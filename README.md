[![GitHub Release](https://img.shields.io/github/release/toreamun/amshan-homeassistant?style=for-the-badge)](https://github.com/toreamun/amshan-homeassistant/releases)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/toreamun/amshan-homeassistant.svg?logo=lgtm&logoWidth=18&style=for-the-badge)](https://lgtm.com/projects/g/toreamun/amshan-homeassistant/context:python)
[![License](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg?style=for-the-badge)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg?style=for-the-badge)](https://www.buymeacoffee.com/toreamun)

# AMS HAN Home Assistant integration

Integrate HAN-port of Aidon, Kaifa and Kamstrum meters used in Norway with Home Assistant. The integration uses [local push](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/), and Home Assistant will be notified as soon as a new measurement is available (2 sec, 10 sec and every hour depending on sensor type and meter type).

This integration supports connecting to MBUS device using serial port or TCP-IP address/port.

![image](https://user-images.githubusercontent.com/12134766/145044580-4c072af7-2bdf-4b6c-894c-38d5789ba9be.png)


## Conecting MBUS device

You need to have a MBUS slave device connected to to the HAN (Home Area Network) port of your meter. The HAN-port is a RJ45 socket where only pin 1 and 2 is used. Connect wires from pin 1 and 2 to the MBUS slave device. Then connect the MBUS device to your computer. Most devices uses USB to become a serial device when connected. You can then relay (i.e. using net2ser and socat) the signal to TCP/IP if your device is connected to a remote computer.

## MBUS device

This integration has been tested with several simple USB devices sold on e-bay. Search for MBUS USB slave. Note that some devices uses EVEN parity (default is ODD) when connecting.

## Setup

Search for AMSHAN on Configuration/Integrations page after installing (most simple is to use [HACS](https://hacs.xyz/)).
Please not that some MBUS serial devices uses EVEN parity (the default is ODD).

When using serial device setup, it is often usefull to use a device-by-id device name on Linux to have a stable device name. You then use a device name starting with /dev/serial/by-id/. You can find the device id in hardware menu of the host if you are running Hassio (select Supervisor -> System -> Host -> ... -> Hardware).

## Options

It is possible to configure a scale factor of currents, power and energy measurements. Some meters are known to to not be connected directly to main power, but through a current transformer with a reduction factor of 50.

## Remote MBUS

You can connect to a remote MBUS device using TCP/IP by selecting connection type "network" in setup.

If your device is connected to a Linux host, then ser2net is a good choice to run on the host to bridge the typical MBUS serial interface to TCP/IP. This [ser2net](https://github.com/cminyard/ser2net) config (/etc/ser2net.conf) line makes a 2400 baud, even parity, 8 data bits and one stop bit serial MBUS device available on TCP/IP port 3001:
`3001:raw:600:/dev/ttyUSB0:2400 8DATABITS EVEN 1STOPBIT`

Similar for ser2net yaml config (/etc/ser2net.yaml):

```
connection: &han
   accepter: tcp,3001
   enable: on
   options:
      kickolduser: true
   connector: serialdev,/dev/ttyUSB0,2400e81,local
```
