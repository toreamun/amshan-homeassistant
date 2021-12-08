[![GitHub Release](https://img.shields.io/github/release/toreamun/amshan-homeassistant?style=for-the-badge)](https://github.com/toreamun/amshan-homeassistant/releases)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/toreamun/amshan-homeassistant.svg?logo=lgtm&logoWidth=18&style=for-the-badge)](https://lgtm.com/projects/g/toreamun/amshan-homeassistant/context:python)
[![License](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg?style=for-the-badge)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg?style=for-the-badge)](https://www.buymeacoffee.com/toreamun)

[English](README.en.md)

# AMS HAN Home Assistant integrasjon

Home Assistant integrasjon for Aidon, Kaifa and Kamstrum AMS-strømmålere tilkoblet via HAN-porten. Integrasjonen benytter [local push](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/), og Home Assistant blir derfor oppdatert umiddelbart etter at måleren har sendt ut nye data på porten (2 sek, 10 sek og hver hele time avhengig av informasjonselement og målertype).

Integrasjonen støtter å lese fra [M-BUS](https://en.wikipedia.org/wiki/Meter-Bus) (også kalt Meter-Bus) enheter tilkoblet via serieport (vanlig for USB-enhenter) eller nettverk (TCP-IP addresse/port). Sistnevnte er ofte aktuelt om Home Assistant kører på en annen maskin en den M-BUS er tilkoblet.

![image](https://user-images.githubusercontent.com/12134766/145044580-4c072af7-2bdf-4b6c-894c-38d5789ba9be.png)

## Tilkobling av M-BUS-enhet

Du trenger å ha en [M-BUS](https://en.wikipedia.org/wiki/Meter-Bus) slave enhet tilkoblet HAN (Home Area Network) porten på din måler. HAN-porten har en RJ45 kontakt, hvor kun pinn 1 og 2 er benyttet. Du må koblie pinn 1 og 2 til de to koblingspunktene på M-BUS-slaveenheten, som så kobles til en datamaskin. De fleste USB-enheter blir da en serieport på datamaskinen. Du kan benytte programvare (f.eks. ser2net eller socat) for å sende data over TCP/IP hvis Home Assistant kjører på en annen datamaskin.

## M-BUS-enhet

Denne integrasjonen har blitt testet med flere ulike enkle M-BUS USB-enheter solgt på e-bay. Flere ulike tilsvarende enheter er også i salg i Norge. Søk etter MBUS USB slave.

## Home Assistant oppsett

Søk etter AMSHAN under integrasjoner etter installasjon (det enkleste er å benytte [HACS](https://hacs.xyz/)).

NB! Noen enheter benytter EVEN parietet (standard er ODD) ved tilkobling. Hvis du får problemer med tilknytning i Home Assistant er pariteten den første innstillingen du bør teste å endre hvis du er sikkert på at enhetsnavnet er riktig.

Når man benytter en USB enhet på Linux er det ofte lurt å benytte device-by-id enhetsnavn slik at enhetsnavnet ikke endrer seg. Da benytter man et enhetsnavn som starter med /dev/serial/by-id/. Du kan finne riktig navn i maskinvarene menyen for host (velg Supervisor -> System -> Host -> ... -> Maskinvare).
![image](https://user-images.githubusercontent.com/12134766/145182598-d3fa3e7b-2784-4f6a-9aed-b90c66de20fa.png)

## Innstillinger

Det er mulig å benytte en skaleringsfaktor for strøm-, effekt- og energimålingene. Noen få målere er ikke tilkoblet direkte til strømnettet, men via en strømomformer med en reduksjonsfaktor som halverer målingene. I det tilfellet kan man benytte skaleringsfaktoren til å få riktige verdier.

## Fjerntilkoblet M-BUS-enhet

Du kan koble det til en nettverkstilkoble M-BUS-enhet ved å velge nettverk ved oppsett.
Hvis enheten din er tilkoblet noe som kjører Linux er [ser2net](https://github.com/cminyard/ser2net) et godt valg.

Denne [ser2net](https://github.com/cminyard/ser2net) konfigurasjonen (/etc/ser2net.conf) gjør en2400 baud, even paritet, 8 data bits and en stop bit USB-serieport M-BUS-enhet tilgjengelig på TCP/IP port 3001:
`3001:raw:600:/dev/ttyUSB0:2400 8DATABITS EVEN 1STOPBIT`

Tilsvarende for [ser2net](https://github.com/cminyard/ser2net) yaml konfigurasjon hvit det er det som benyttes (/etc/ser2net.yaml):

```
connection: &han
   accepter: tcp,3001
   enable: on
   options:
      kickolduser: true
   connector: serialdev,/dev/ttyUSB0,2400e81,local
```
