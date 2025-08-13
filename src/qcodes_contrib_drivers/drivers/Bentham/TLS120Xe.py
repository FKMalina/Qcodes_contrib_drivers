from __future__ import annotations

import time
from typing import Tuple, List

from qcodes.instrument.visa import VisaInstrument


class TLS120Xe(VisaInstrument):
    """
    QCoDeS VISAInstrument driver for the Bentham TLS120Xe tuneable light source.

    This driver uses a USB RAW VISA resource and implements the device's HID/SCPI
    messaging rules atop VisaInstrument:
    - Commands are ASCII, newline-terminated.
    - Each command line must be <= 64 bytes including terminator.
    - Replies arrive as a single up-to-64-byte packet, ASCII, NUL-terminated.

    Address
    -------
    Use a USB RAW VISA resource name, for example:
      'USB0::0x1234::0x5678::ABC123::RAW'
    Replace vendor ID, product ID, and serial with your device’s values.
    A working libusb backend (pyvisa-py) and appropriate OS permissions are required.

    Exposed parameters
    ------------------
    wavelength (get): current wavelength [nm]
    wavelength_target (get/set): target wavelength [nm] (set does not move)
    at_target (get): 1 when emitting at target wavelength
    lamp (get/set): 1 lamp on, 0 lamp off
    lamp_boot (get/set): 1 auto-on at boot
    lamp_timeout_ms (get/set): ignition timeout [ms]
    mono_speed_percent (get/set): monochromator speed [% of default, 1–100]
    state (get): system operating state string
    burntime_hours (get): cumulative lamp-on time since last reset
    measured_current_a (get), measured_voltage_v (get), measured_power_w (get)
    pd_current_a (get), pd_current_median_a (get), pd_current_max_a (get)

    Typical usage
    -------------
    >>> tls = TLS120Xe('tls', address='USB0::0xVVVV::0xPPPP::SERIAL::RAW')
    >>> tls.set_remote(True)
    >>> tls.lamp(True)
    >>> tls.go_to_wavelength(500.0, wait=True)
    >>> print(tls.at_target())

    Reference
    ---------
    TLS120Xe Communications Manual, version 1.7.0
    """

    _MAX_LINE = 64  # HID report size in bytes

    def __init__(
        self,
        name: str,
        address: str,
        *,
        visalib: str | None = None,
        timeout: float = 2.0,
    ) -> None:
        super().__init__(name, address=address, visalib=visalib, terminator="", timeout=timeout)

        # Add QCoDeS parameters

        self.add_parameter(
            "wavelength",
            unit="nm",
            label="Current wavelength",
            get_cmd=self._get_wavelength,
            docstring="Current monochromator wavelength from :MONO:WAVE? (first value).",
        )

        self.add_parameter(
            "wavelength_target",
            unit="nm",
            label="Target wavelength",
            get_cmd=self._get_wavelength_target,
            set_cmd=self._set_wavelength_target,
            docstring="Target wavelength via :MONO:WAVE <wl>. Does not move; call move() or go_to_wavelength().",
        )

        self.add_parameter(
            "at_target",
            get_cmd=lambda: bool(int(self.ask(":OUTP:ATTarget?"))),
            docstring="True if emitting at target wavelength (:OUTP:ATTarget?).",
        )

        self.add_parameter(
            "lamp",
            get_cmd=lambda: bool(int(self.ask(":LAMP?"))),
            set_cmd=lambda v: self.write(f":LAMP {1 if v else 0}"),
            docstring="Lamp on/off (:LAMP, :LAMP?).",
        )

        self.add_parameter(
            "lamp_boot",
            get_cmd=lambda: bool(int(self.ask(":LAMP:BOOT?"))),
            set_cmd=lambda v: self.write(f":LAMP:BOOT {1 if v else 0}"),
            docstring="Lamp auto-on at boot (:LAMP:BOOT, :LAMP:BOOT?).",
        )

        self.add_parameter(
            "lamp_timeout_ms",
            unit="ms",
            get_cmd=lambda: int(self.ask(":LAMP:TIMEout?")),
            set_cmd=lambda v: self.write(f":LAMP:TIMEout {int(v)}"),
            docstring="Lamp ignition timeout in milliseconds (:LAMP:TIMEout, :LAMP:TIMEout?).",
        )

        self.add_parameter(
            "mono_speed_percent",
            unit="%",
            get_cmd=lambda: float(self.ask(":MONO:SPEED?")),
            set_cmd=lambda v: self.write(f":MONO:SPEED {float(v)}"),
            docstring="Monochromator speed as percent of default (1–100).",
        )

        self.add_parameter(
            "state",
            get_cmd=lambda: self.ask(":SYST:OPER:STAT?"),
            docstring="Operating state string (e.g. AT_TARGET, MOVING_TO_TARGET, LAMP_OFF).",
        )

        self.add_parameter(
            "burntime_hours",
            unit="h",
            get_cmd=lambda: float(self.ask(":FETCh:BURNtime?")),
            docstring="Cumulative lamp-on time in hours since last burntime reset.",
        )

        # Electrical measurements
        self.add_parameter(
            "measured_current_a",
            unit="A",
            get_cmd=lambda: float(self.ask(":MEAS:CURR?")),
            docstring="Measured lamp current in A (:MEAS:CURR?).",
        )
        self.add_parameter(
            "measured_voltage_v",
            unit="V",
            get_cmd=lambda: float(self.ask(":MEAS:VOLT?")),
            docstring="Measured lamp voltage in V (:MEAS:VOLT?).",
        )
        self.add_parameter(
            "measured_power_w",
            unit="W",
            get_cmd=lambda: float(self.ask(":MEAS:POW?")),
            docstring="Measured electrical power in W (:MEAS:POW?).",
        )

        # Photodiode feedback currents
        self.add_parameter(
            "pd_current_a",
            unit="A",
            get_cmd=lambda: float(self.ask(":MEAS:CURR:PD?")),
            docstring="Latest feedback photodiode current in A.",
        )
        self.add_parameter(
            "pd_current_median_a",
            unit="A",
            get_cmd=lambda: float(self.ask(":MEAS:CURR:PD:MED?")),
            docstring="Median of the last 50 PD samples (~0.5 s) in A.",
        )
        self.add_parameter(
            "pd_current_max_a",
            unit="A",
            get_cmd=lambda: float(self.ask(":MEAS:CURR:PD:MAX?")),
            docstring="Session-maximum photodiode current in A.",
        )

        # Verify communication
        _ = self.get_idn()

    # ------------------------- VISA raw I/O overrides ------------------------- #

    def write(self, cmd: str) -> None:
        """
        Send a single SCPI command as ASCII with newline termination.

        Ensures the command payload length does not exceed 64 bytes including
        the newline terminator, as required by the device's HID report size.
        """
        if not cmd.endswith("\n"):
            cmd = cmd + "\n"
        payload = cmd.encode("ascii", "strict")
        if len(payload) > self._MAX_LINE:
            raise ValueError(
                f"Command too long for TLS120Xe HID line: {len(payload)} bytes "
                "(max 64). Send one SCPI command per write."
            )
        # Write raw bytes through VISA (USB RAW)
        self.write_raw(payload)

    def read(self) -> str:
        """
        Read one reply packet (up to 64 bytes), strip at first NUL, decode ASCII.
        """
        data = bytes(self.read_bytes(self._MAX_LINE))
        if not data:
            raise TimeoutError("TLS120Xe VISA read timeout.")
        if b"\x00" in data:
            data = data.split(b"\x00", 1)[0]
        return data.decode("ascii", "ignore")

    def ask(self, cmd: str) -> str:
        """
        Send a SCPI query and return the reply string without terminators.
        """
        if not cmd.endswith("?"):
            raise ValueError("ask() must be used with a SCPI query ending in '?'.")
        self.write(cmd)
        return self.read()

    # ------------------------------ ID and errors ----------------------------- #

    def get_idn(self) -> dict:
        """
        Return identification info parsed from *IDN?.
        """
        raw = self.ask("*IDN?")
        parts = [p.strip().strip('"') for p in raw.split(",")]
        while len(parts) < 4:
            parts.append("")
        return {"vendor": parts[0], "model": parts[1], "serial": parts[2], "firmware": parts[3]}

    def system_error_count(self) -> int:
        "Return the number of queued errors (:SYST:ERR:COUNT?)."
        return int(self.ask(":SYST:ERR:COUNT?"))

    def system_error_next(self) -> Tuple[int, str]:
        "Pop and return the next error as (code, message)."
        raw = self.ask(":SYST:ERR:NEXT?")
        try:
            code_s, msg_s = raw.split(",", 1)
        except ValueError:
            return 0, raw.strip()
        return int(code_s), msg_s.strip().strip('"')

    def check_errors(self) -> List[Tuple[int, str]]:
        "Retrieve and clear all pending errors."
        out: List[Tuple[int, str]] = []
        while True:
            n = self.system_error_count()
            if n <= 0:
                break
            out.append(self.system_error_next())
        return out

    # --------------------------- Wavelength utilities -------------------------- #

    def _get_wavelength_pair(self) -> Tuple[float, float]:
        """
        Return (current, target) wavelengths in nm from :MONO:WAVE?.
        """
        raw = self.ask(":MONO:WAVE?")
        cur_s, tgt_s = raw.split(",")
        return float(cur_s), float(tgt_s)

    def _get_wavelength(self) -> float:
        wl, _ = self._get_wavelength_pair()
        return wl

    def _get_wavelength_target(self) -> float:
        _, tgt = self._get_wavelength_pair()
        return tgt

    def _set_wavelength_target(self, wavelength_nm: float) -> None:
        """
        Set target wavelength in nm with :MONO:WAVE <wl>. This does not move.
        """
        self.write(f":MONO {float(wavelength_nm)}")

    # ------------------------------- Motion control ---------------------------- #

    def move(self, *, wait: bool = True, timeout: float = 60.0, poll: float = 0.1) -> bool:
        """
        Move to current targets (:MONO:MOVE?). Optionally wait for at-target.

        Returns True on success. Raises RuntimeError on failure or timeout.
        """
        ok = bool(int(self.ask(":MONO:MOVE?")))
        if not ok:
            code, msg = self.system_error_next()
            raise RuntimeError(f"Move failed: {code}, {msg}")
        if wait:
            t0 = time.time()
            while time.time() - t0 < timeout:
                if self.at_target():
                    return True
                time.sleep(poll)
            raise RuntimeError("Timed out waiting for at-target after MOVE.")
        return True

    def move_async(self) -> None:
        "Start movement without waiting (:MONO:MOVE:ASYNC)."
        self.write(":MONO:MOVE:ASYNC")

    def park(self, *, wait: bool = True, timeout: float = 30.0, poll: float = 0.2) -> bool:
        """
        Park the monochromator (:MONO:PARK?). Optionally wait until idle.
        """
        ok = bool(int(self.ask(":MONO:PARK?")))
        if not ok:
            code, msg = self.system_error_next()
            raise RuntimeError(f"Park failed: {code}, {msg}")
        if wait:
            t0 = time.time()
            while time.time() - t0 < timeout:
                st = self.ask(":MONO:STAT?")
                if st in ("idle", "not_initialized"):
                    return True
                time.sleep(poll)
        return True

    def go_to_wavelength(
        self,
        wavelength_nm: float,
        *,
        wait: bool = True,
        timeout: float = 90.0,
        poll: float = 0.1,
    ) -> bool:
        """
        Select a valid grating/filter for the requested wavelength and move there.

        Issues :MONO:GOTO? <wl> followed by :MONO:MOVE?.
        Raises RuntimeError if the GOTO fails, the move fails, or waiting times out.
        """
        raw = self.ask(f":MONO:GOTO? {float(wavelength_nm)}")
        try:
            success_s, status_s = raw.split(",", 1)
        except ValueError:
            raise RuntimeError(f"Unexpected GOTO? reply: {raw!r}")
        success = bool(int(success_s))
        status = status_s.strip().strip('"')
        if not success:
            raise RuntimeError(f"GOTO failed for {wavelength_nm} nm: {status}")
        return self.move(wait=wait, timeout=timeout, poll=poll)

    # ----------------------------- White-light mode ---------------------------- #

    def set_white_output(self, intensity: float) -> None:
        """
        Set output to white light by detuning towards zero order (:OUTP:WHITe <intensity>).

        intensity is a float in [0, 1] where 1 is maximum brightness.
        """
        self.write(f":OUTP:WHITe {float(intensity)}")

    # ------------------------------- Maintenance ------------------------------- #

    def reset_burntime(self) -> None:
        "Reset the burntime counter (:RESET:BURNtime)."
        self.write(":RESET:BURNtime")

    def set_remote(self, enable: bool = True) -> None:
        "Enable remote or local mode (SYST:REM / SYST:LOC)."
        self.write("SYST:REM" if enable else "SYST:LOC")
