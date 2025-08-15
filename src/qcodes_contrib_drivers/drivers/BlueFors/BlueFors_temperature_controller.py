import io
import sys
import time
from datetime import datetime, timedelta

import requests
from qcodes import Instrument, InstrumentChannel
from qcodes.validators import Numbers, Bool


class BlueforsHeater(InstrumentChannel):
    """
    QCoDeS InstrumentChannel class for a Bluefors Heater.
    """

    def __init__(self, parent, name, heater_number):
        super().__init__(parent, name)
        self.heater_number = heater_number

        self.add_parameter(
            "status",
            get_cmd=self.get_status,
            set_cmd=self.set_status,
            vals=Bool(),
            label="Heater Status",
            docstring="Turn the heater on (True) or off (False).",
        )

        self.add_parameter(
            "power",
            get_cmd=self.get_power,
            set_cmd=self.set_power,
            unit="W",
            label="Heater Power",
            docstring="Power of the heater.",
            vals=Numbers(0, 1),
        )

        self.add_parameter(
            "mode",
            get_cmd=self.get_mode,
            set_cmd=self.set_mode,
            vals=Numbers(0, 1),
            label="Control Mode",
            docstring="Set heater control mode: 0 for Manual, 1 for PID.",
        )

        self.add_parameter(
            "pid_p",
            get_cmd=lambda: self.get_pid_param("proportional"),
            set_cmd=lambda value: self.set_pid_param("proportional", value),
            label="PID Proportional Gain",
        )

        self.add_parameter(
            "pid_i",
            get_cmd=lambda: self.get_pid_param("integral"),
            set_cmd=lambda value: self.set_pid_param("integral", value),
            label="PID Integral Gain",
        )

        self.add_parameter(
            "pid_d",
            get_cmd=lambda: self.get_pid_param("derivative"),
            set_cmd=lambda value: self.set_pid_param("derivative", value),
            label="PID Derivative Gain",
        )

        self.add_parameter(
            "setpoint",
            get_cmd=self.get_setpoint,
            set_cmd=self.set_setpoint,
            unit="K",
            label="Setpoint Temperature",
            docstring="Temperature setpoint for PID control.",
        )

    def get_status(self):
        url = f"{self.root_instrument.base_url}/heater"
        response = requests.post(url, json={"heater_nr": self.heater_number})
        response.raise_for_status()
        data = response.json()
        return data["active"]

    def set_status(self, status):
        url = f"{self.root_instrument.base_url}/heater/update"
        response = requests.post(url, json={"heater_nr": self.heater_number, "active": status})
        response.raise_for_status()
        return response.json()

    def get_power(self):
        url = f"{self.root_instrument.base_url}/heater"
        response = requests.post(url, json={"heater_nr": self.heater_number})
        response.raise_for_status()
        data = response.json()
        return data["power"]

    def set_power(self, power):
        url = f"{self.root_instrument.base_url}/heater/update"
        response = requests.post(url, json={"heater_nr": self.heater_number, "power": power})
        response.raise_for_status()
        return response.json()

    def get_mode(self):
        url = f"{self.root_instrument.base_url}/heater"
        response = requests.post(url, json={"heater_nr": self.heater_number})
        response.raise_for_status()
        data = response.json()
        return data["pid_mode"]

    def set_mode(self, mode):
        url = f"{self.root_instrument.base_url}/heater/update"
        response = requests.post(url, json={"heater_nr": self.heater_number, "pid_mode": mode})
        response.raise_for_status()
        return response.json()

    def get_pid_param(self, param):
        url = f"{self.root_instrument.base_url}/heater"
        response = requests.post(url, json={"heater_nr": self.heater_number})
        response.raise_for_status()
        data = response.json()
        return data["control_algorithm_settings"][param]

    def set_pid_param(self, param, value):
        url = f"{self.root_instrument.base_url}/heater/update"
        control_algorithm_settings = {param: value}
        response = requests.post(
            url,
            json={
                "heater_nr": self.heater_number,
                "control_algorithm_settings": control_algorithm_settings,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_setpoint(self):
        url = f"{self.root_instrument.base_url}/heater"
        response = requests.post(url, json={"heater_nr": self.heater_number})
        response.raise_for_status()
        data = response.json()
        return data["setpoint"]

    def set_setpoint(self, setpoint):
        url = f"{self.root_instrument.base_url}/heater/update"
        response = requests.post(url, json={"heater_nr": self.heater_number, "setpoint": setpoint})
        response.raise_for_status()
        return response.json()


class BlueforsChannel(InstrumentChannel):
    """
    QCoDeS InstrumentChannel class for a Bluefors Temperature Channel.
    """

    def __init__(self, parent, name, channel_number):
        super().__init__(parent, name)
        self.channel_number = channel_number

        self.add_parameter(
            "temperature",
            get_cmd=self.get_temperature,
            unit="K",
            label="Temperature",
            docstring="Temperature of the channel.",
        )

        self.add_parameter(
            "heater",
            get_cmd=self.get_heater,
            set_cmd=self.set_heater,
            docstring="Get or set the heater coupled to this channel.",
            vals=Numbers(0, 4),
        )

    def get_temperature(self):
        stop_time = datetime.utcnow()
        start_time = stop_time - timedelta(minutes=15)
        stop_time_str = stop_time.isoformat() + "Z"
        start_time_str = start_time.isoformat() + "Z"

        historical_data = self.root_instrument.get_historical_data(self.channel_number, start_time_str, stop_time_str)
        measurements = historical_data.get("measurements", {})
        timestamps = measurements.get("timestamp", [])
        temperatures = measurements.get("temperature", [])

        if not timestamps or not temperatures:
            print(f"No updated measurement within 15 minutes for channel {self.channel_number}")
            return None

        latest_index = timestamps.index(max(timestamps))
        latest_time = datetime.utcfromtimestamp(timestamps[latest_index])
        latest_temp = temperatures[latest_index]

        # print(f"Channel {self.channel_number} ({self.name}):")
        # print(f"  Last Measurement: {latest_temp} K at {latest_time}")
        return latest_temp

    def get_heater(self):
        url = f"{self.root_instrument.base_url}/channel"
        response = requests.post(url, json={"channel_nr": self.channel_number})
        response.raise_for_status()
        data = response.json()
        return data["coupled_heater_nr"]

    def set_heater(self, heater_number):
        url = f"{self.root_instrument.base_url}/channel/heater/update"
        response = requests.post(url, json={"channel_nr": self.channel_number, "heater_nr": heater_number})
        response.raise_for_status()
        return response.json()


class BlueforsTemperatureController(Instrument):
    """
    QCoDeS driver for the Bluefors Temperature Controller (web API).

    This instrument discovers all temperature channels and heaters from the
    controller and exposes them as QCoDeS submodules:

    Channels: available under attributes channel_<sanitized_name>
    Heaters: available under attributes heater_<sanitized_name>
    Names are taken from the controller and sanitized by replacing spaces/dashes
    with underscores. If a name is empty, the numeric ID is used.

    The driver communicates with the controller over HTTP and raises
    requests.HTTPError on non-2xx responses.

    Args:
        name: QCoDeS instrument name.
        ip_address: IP or hostname of the Bluefors controller.
        port: HTTP port (default 5001).

    ___Common tasks and examples___

    Create the instrument and inspect device info
    >>> tc = BlueforsTemperatureController("bf", "192.168.0.10", port=5001)
    >>> tc.idn.get()
    {'fw_version': '...', 'serial': '...', ...}

    List discovered channels and heaters
    >>> tc.get_channel_names()
    {1: 'MXC', 2: 'Still', 3: '4K'}
    >>> tc.get_heater_info()
    {'data': [{'heater_nr': 1, 'name': 'MXC Heater'}, ...]}

    Access a channel/heater by name
    >>> ch = tc.channel_MXC          # BlueforsChannel
    >>> ht = tc.heater_MXC_Heater    # BlueforsHeater

    Read the latest temperature of a channel
    >>> ch.temperature.get()
    0.0135
    Notes:
    - The channel temperature getter fetches historical data for the last
      15 minutes and returns the most recent sample. If no sample is found,
      it returns None and prints a message.

    Couple a channel to a heater (feedback source)
    >>> ch.heater()
    0
    >>> ch.heater(1)             # Couple channel MXC to heater number 1
    >>> ch.heater()
    1

    Manual heater control (open-loop)
    >>> ht.mode(0)               # 0 = Manual, 1 = PID
    >>> ht.status(True)             # Turn heater output ON
    >>> ht.power(0.25)           # Set fractional power 0.0–1.0
    >>> ht.power()
    0.25
    >>> ht.status(False)             # Turn heater output OFF

    PID control (closed-loop)
    - Ensure the heater is coupled to the intended temperature channel.
    - Set PID gains and the temperature setpoint (in kelvin).
    - Enable PID mode and turn the heater on.

    >>> ch.heater(1)             # Couple channel to this heater
    >>> ht.pid_p(10.0)
    >>> ht.pid_i(0.5)
    >>> ht.pid_d(0.0)
    >>> ht.setpoint(0.015)       # 15 mK
    >>> ht.mode(1)               # PID mode
    >>> ht.status(True)             # Enable output

    Query current heater state
    >>> ht.status()              # 0 or 1
    >>> ht.mode()                # 0 (Manual) or 1 (PID)
    >>> ht.setpoint()
    0.015
    >>> ht.get_power()
    0.25
    """

    def __init__(self, name, ip_address, port=5001, **kwargs):
        super().__init__(name, **kwargs)
        self.ip_address = ip_address
        self.port = port
        self.base_url = f"http://{self.ip_address}:{self.port}"

        self.add_parameter(
            "idn",
            get_cmd=self.get_idn,
            docstring="Get the device identification information.",
        )

        self.create_channels()
        self.create_heaters()

    def get_idn(self):
        url = f"{self.base_url}/system"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data

    def get_channel_names(self):
        url = f"{self.base_url}/channels"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return {ch["channel_nr"]: ch["name"].replace(" ", "_").replace("-", "_") for ch in data["data"]}

    def get_historical_data(self, channel, start_time, stop_time):
        url = f"{self.base_url}/channel/historical-data"
        data = {
            "channel_nr": channel,
            "start_time": start_time,
            "stop_time": stop_time,
            "fields": ["timestamp", "temperature"],
        }
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()

    def create_channels(self):
        """
        Dynamically create channel objects based on the number of channels available on the device.
        """
        channel_names = self.get_channel_names()
        for channel_number, channel_name in channel_names.items():
            channel_name = channel_name.replace(" ", "_").replace("-", "_")
            if channel_name == "":
                channel_name = str(channel_number)
            channel = BlueforsChannel(self, channel_name, channel_number)
            self.add_submodule(f"channel_{channel_name}", channel)

    def get_heater_info(self):
        url = f"{self.base_url}/heaters"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data

    def create_heaters(self):
        """
        Dynamically create heater objects based on the number of heaters available on the device.
        """
        heater_info = self.get_heater_info()
        for heater in heater_info["data"]:
            heater_number = heater["heater_nr"]
            heater_name = heater["name"].replace(" ", "_").replace("-", "_")
            if heater_name == "":
                heater_name = str(heater_number)
            heater = BlueforsHeater(self, heater_name, heater_number)
            self.add_submodule(f"heater_{heater_name}", heater)
