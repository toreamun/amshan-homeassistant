[![GitHub Release](https://img.shields.io/github/release/toreamun/amshan-homeassistant?style=for-the-badge)](https://github.com/toreamun/amshan-homeassistant/releases)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/toreamun/amshan-homeassistant.svg?logo=lgtm&logoWidth=18&style=for-the-badge)](https://lgtm.com/projects/g/toreamun/amshan-homeassistant/context:python)
[![License](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![Project Maintenance](https://img.shields.io/badge/maintainer-Tore%20Amundsen%20%40toreamun-blue.svg?style=for-the-badge)
[![buy me a coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-orange.svg?style=for-the-badge)](https://www.buymeacoffee.com/toreamun)

[English](README.en.md)

# AMS HAN Home Assistant integrasjon
**Home Assistant integrasjon for Aidon, Kaifa and Kamstrum AMS-strømmålere. Itegrasjonen støter både streaming (serieport/TCP-IP) og MQTT. [Tibber Pulse](https://tibber.com/no/store/produkt/pulse) kan settes opp til å publisere til lokal MQTT som denne integrasjonen kan benytte.**

Integrasjonen benytter [local push](https://www.home-assistant.io/blog/2016/02/12/classifying-the-internet-of-things/), og Home Assistant blir derfor oppdatert umiddelbart etter at måleren har sendt ut nye data på porten (2 sekund, 10 sekund, og hver hele time, avhengig av informasjonselement og målertype).

Flere målere kan være tilknyttet samme Home Assistant installasjon.

![image](https://user-images.githubusercontent.com/12134766/145044580-4c072af7-2bdf-4b6c-894c-38d5789ba9be.png)

![image](https://user-images.githubusercontent.com/12134766/150021268-28f01386-0583-4f76-9b78-b35882d2019e.png)


## Benytte Tibber Pulse
[Tibber Pulse](https://tibber.com/no/store/produkt/pulse) publiserer normalt meldinger fra målerens datastrøm til en MQTT-server i skyen. Man kan sette opp Tibber Pulse til å publisere til et topic på en lokal MQTT-server (f.eks Home Assistant Mosquitto broker Add-On), og sette denne integrasjonen opp til å lytte på disse meldingene. Merk at man da ikke får målingene i Tibber Appen, ettersom måligene ikke lenger sendes til Tibber sin MQTT-server. [ElWiz har en veiledning](https://github.com/iotux/ElWiz#oppsett-av-pulse) til å sette opp MQTT på Tibber Pulse.

Hvis du bestemmer deg for å kjøpe en Tibber Pulse for å benytte med denne integrasjonen er det fint om du benytter denne [invitasjonen](https://tibber.com/no/invite/230c1af6) med vevekode `230c1af6`. I skrivende stund gir invitasjonen 500 kr til bruk i nettbutikken hvor du kan kjøpe Tibber Pulse hvis du blir kunde hos dem. Det er selvsagt ingen garanti for at Tibber ikke kommer med firmware endringer som gjør noe med muligheten for å sette opp lokal MQTT.

## MQTT uten bruk av Tibber Pulse
Integrasjonen kan motta binære målermeldinger fra MQTT. Meldingene kan være hele HDLC-frame (både med og uten flag-sequence) slik de sendes fra måler, eller bare selve målerdatane fra innholdet av HDLC-frame.

## M-BUS-enhet
Integrasjonen støtter streaming fra [M-BUS](https://en.wikipedia.org/wiki/Meter-Bus) (også kalt Meter-Bus) enheter tilkoblet via serieport (vanlig for USB-enhenter) eller nettverk (TCP-IP addresse/port). Sistnevnte er ofte aktuelt om Home Assistant kjører på en annen maskin en den M-BUS er tilkoblet.

Du trenger å ha en [M-BUS](https://en.wikipedia.org/wiki/Meter-Bus) slave enhet tilkoblet HAN (Home Area Network) porten på din måler. HAN-porten har en RJ45 kontakt, hvor kun pinn 1 og 2 er benyttet. Du må koble pinn 1 og 2 til de to koblingspunktene på M-BUS-slaveenheten, som så kobles til en datamaskin. De fleste USB-enheter blir da en serieport på datamaskinen. Du kan benytte programvare (f.eks. `ser2net` eller `socat`) for å sende data over TCP/IP hvis Home Assistant kjører på en annen datamaskin.

![image](https://user-images.githubusercontent.com/12134766/146074371-e3e4468a-7f5c-4ed6-8496-073666c1b0de.png)

### Kjøpe MBUS USB slave
Denne integrasjonen har blitt testet med flere ulike enkle M-BUS USB-enheter solgt på [eBay](https://www.ebay.com/sch/i.html?_nkw=mbus+usb+slave) og [AliExpress](https://www.aliexpress.com/premium/mbus-usb-slave.html). Søk etter MBUS USB slave. **Det er rapportert om problemer med en type som ser ut som en svart boks med ledning.** Ellers ser det meste ut til å fungere. Rapporter gjerne dine erfaringer.


## Home Assistant oppsett
Integrasjonen er en Home Assistant Custom integration. Den enkleste måten er å laste den ned med [HACS](https://hacs.xyz/). Da får du også varsel om oppdateringer fra HACS i Home Assistant.

### Nedlasting med HACS
- Velg HACS i hovedmenyen
- Velg Integrations
- Velg på "Explore & download repositories"
- Søk etter AMSHAN og velg dette
- Velg "Download this repository with HACS"
- Velg "Download"
- Restart Home Assistant
- Tøm nettleseren sin cache. Hvis du ikke gjør dette risikerer du å ikke finne integrasjonen i listen av tilgjengelige integrasjoner.


### Nedlasting uten HACS på Home Assistant OS
- Gå til Supervisor panel og installer en SSH add-on
- Start SSH add-on
- Gå til SSH add-on
- Bytt katalog til config
- Lag katalogen custom_components hvis den ikke eksisterer.
- Bytt katalog til custom_components
- Last ned git repoet
```
git clone https://github.com/toreamun/amshan-homeassistant amshan
```
- Restart Home Assistant
- Tøm nettleseren sin cache. Hvis du ikke gjør dette risikerer du å ikke finne integrasjonen i listen av tilgjengelige integrasjoner.

### Nedlasting uten HACS i container
- Åpne en terminal
- Bytt katalog Home Assistant sin config katalog
- Lag katalogen custom_components hvis den ikke eksisterer.
- Bytt katalog til custom_components
- Last ned git repoet
```
git clone https://github.com/toreamun/amshan-homeassistant amshan
```
- Tøm nettleseren sin cache. Hvis du ikke gjør dette risikerer du å ikke finne integrasjonen i listen av tilgjengelige integrasjoner.

### Installasjon av integrasjonen
Når integrasjonen er lastet ned, Home Assistant er restartet og nettleser cahce er tømt installeres integrasjonen på samme måte som andre Home Assistant integrasjoner. Søk etter amshan og legg den til (tøm nettleser cahce hvis du ikke finner amshan):

![image](https://user-images.githubusercontent.com/12134766/150140185-a595e7e4-3734-4215-aea6-308c94646387.png)

Velg type tilkobling:

![image](https://user-images.githubusercontent.com/12134766/150011471-424d58fb-efca-437d-9e3f-878fbfe0edc9.png)

#### MQTT
For å kunne velge MQTT må du først ha satt opp MQTT-integrasjonen i Home Assistant. Ved oppsett av AMDHAN integrasjonen legger du inn MQTT topic som HAN-port adapter publiserer til. Ved bruk av Tibbe Pulse er dette samme topic som er lagt inn for mqtt_topic i oppsett av Tibber Pulse. Hvis du har en adapter som publiserer de ulike listene som måleren sender til ulike topic kan du legge inn flere separert med komma.

#### Serieport
NB! Noen enheter benytter EVEN paritet (standard er ODD) ved tilkobling. Hvis du får problemer med tilknytning i Home Assistant er pariteten den første innstillingen du bør teste å endre hvis du er sikker på at enhetsnavnet er riktig.

Når man benytter en USB enhet på Linux er det ofte lurt å benytte device-by-id enhetsnavn slik at enhetsnavnet ikke endrer seg. Da benytter man et enhetsnavn som starter med `/dev/serial/by-id/`. Du kan finne riktig navn i menyen for host (velg Supervisor -> System -> Host -> ... -> Maskinvare).
![image](https://user-images.githubusercontent.com/12134766/145182598-d3fa3e7b-2784-4f6a-9aed-b90c66de20fa.png)

#### Innstillinger
Det er mulig å benytte en skaleringsfaktor for strøm-, effekt- og energimålingene. Noen få målere er ikke tilkoblet direkte til strømnettet, men via en strømomformer med en reduksjonsfaktor som halverer målingene. I det tilfellet kan man benytte skaleringsfaktoren til å få riktige verdier.

## Fjerntilkoblet M-BUS-enhet
Du kan koble det til en nettverkstilkoblet M-BUS-enhet ved å velge nettverk ved oppsett.
Hvis enheten din er tilkoblet noe som kjører Linux, er [ser2net](https://github.com/cminyard/ser2net) et godt valg.

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
