<img src="https://github.com/home-assistant/brands/blob/master/custom_integrations/amshan/icon.png" width="128" alt="logo">

[![GitHub Release](https://img.shields.io/github/release/toreamun/amshan-homeassistant?style=for-the-badge)](https://github.com/toreamun/amshan-homeassistant/releases)
[![License](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg?style=for-the-badge)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg?style=for-the-badge)](https://www.buymeacoffee.com/toreamun)

[English](README.en.md)

# AMS HAN Home Assistant integrasjon

Home Assistant integrasjon for norske og svenske strømmålere. Både DLMS og P1 fortmater støttes. Integrasjonen skal i prinsippet fungere med alle typer leserer som videresender datastrømmen fra måleren direkte ([serieport/TCP-IP](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-serieport-og-nettverk)) eller oppdelt som [meldinger til MQTT](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-MQTT). Noen aktuelle lesere er:
| Leser | stream/MQTT | DLMS/P1 |Land|
| ------------------------------------------------------------------------------------------------- | ----------- | ---------- |--|
| [Tibber Pulse](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-MQTT#tibber-pulse) | MQTT | DLMS og P1 | NO, SE|
| [energyintelligence.se P1 elmätaravläsare](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-MQTT#energyintelligencese-p1-elm%C3%A4taravl%C3%A4sare) | MQTT | P1 | SE |
| [AmsToMqttBridge og amsleser.no](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-MQTT#amstomqttbridge-og-amsleserno) [ver 2.1](https://github.com/gskjold/AmsToMqttBridge/milestone/22) | MQTT | DLMS | NO, SE? |
| [M-BUS slave](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-serieport-og-nettverk#m-bus-enhet) | stream | DLMS | NO, SE |
| [Oss brikken](https://github.com/toreamun/amshan-homeassistant/wiki/Lesere-serieport-og-nettverk#oss-brikken) | stream | DLMS | NO |

Integrasjonen benytter [local push](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/), og Home Assistant blir derfor oppdatert umiddelbart etter at måleren har sendt ut nye data på porten (2 sekund, 10 sekund, og hver hele time, avhengig av informasjonselement og målertype). Flere målere kan være tilknyttet samme Home Assistant installasjon.

**Se [Wiki](https://github.com/toreamun/amshan-homeassistant/wiki/) for installasjon og tips.**

# Home assistant muligheter

![image](https://user-images.githubusercontent.com/12134766/150297088-535246b1-bd95-406c-8f52-6007a6220e6d.png)

Totalmålingene for import og eksport (aktuelt hvis du produserer strøm) kan kobles til [Home Assistant Energy](https://www.home-assistant.io/blog/2021/08/04/home-energy-management/):

![image](https://user-images.githubusercontent.com/12134766/150021268-28f01386-0583-4f76-9b78-b35882d2019e.png)

Sensorene for spenning og forbruk kan man f.eks selv sette opp i Home Assistant som sensor ("speedometer") eller historikk (graf).

![image](https://user-images.githubusercontent.com/12134766/150298075-d21617c5-7e17-44b3-8fc7-196af9f22f08.png)
