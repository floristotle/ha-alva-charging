# Alva Charging — Home Assistant integration

> ⚠️ **Persoonlijk project — niet aanbevolen voor anderen om te installeren**
>
> Deze integratie is gebouwd voor mijn eigen gebruik (de laadpaal van mijn
> schoonouders) in samenwerking met [Claude Code](https://claude.com/code).
> Het is een reverse-engineering van een private, ongedocumenteerde API
> (Scoptvision) waarvoor geen publieke specificatie bestaat. Ik onderhoud dit
> niet actief en geef geen support. De code kan op elk moment breken wanneer
> Alva of Scoptvision hun API aanpassen.
>
> Als je toch interesse hebt: gebruik op eigen risico, fork hem, en verwacht
> dat je 'm zelf moet onderhouden.

Een Home Assistant custom integration die de Alva Charging cloud
(Scoptvision API) uitleest. Stelt de status van een Alva-laadpaal
(Alfen Eve Single NG910) beschikbaar als sensors.

## Wat krijg je?

- **Cumulatieve geladen energie** (kWh, `total_increasing`) — geschikt voor het
  Energy Dashboard
- **Actueel laadvermogen** (W)
- **Actueel netvermogen** (W)
- **Laadstatus** (charging / paused / idle)
- **Laadmodus** (solar / autopilot / boost)
- **Laadbehoefte** (km)
- **Maandpiek** (W)
- **Sessie-starttijd**
- **Zon-besparing** (EUR)
- Binary sensors: `auto_verbonden`, `laadpaal_online`, `aan_het_laden`

## Installatie via HACS

1. Voeg deze repo toe als **custom repository** in HACS:
   - HACS → driepuntsmenu rechtsboven → **Custom repositories**
   - URL: `https://github.com/floristotle/ha-alva-charging`
   - Categorie: **Integration**
2. Zoek **"Alva Charging"** in HACS en download
3. Herstart Home Assistant
4. **Instellingen → Apparaten en services → Integratie toevoegen → Alva Charging**
5. Vul je e-mailadres + wachtwoord van `slimladen.alva-charging.nl` in

## Energy Dashboard koppelen

Geen Riemann-helper nodig — de integratie levert direct een `total_increasing`
kWh-sensor.

1. **Instellingen → Dashboards → Energie → Individuele apparaten → Apparaat toevoegen**
2. Selecteer `sensor.alva_charging_totaal_geladen`

> De cumulatieve teller start op 0 kWh bij installatie. Eerder geladen energie
> (van vóór installatie) wordt niet meegeteld.

## Hoe werkt het onder de motorkap?

- Authenticatie via AWS Cognito (User Pool `eu-central-1_5xHk0jl2i`)
- Polling van `realtime_data/`, `powerconnect_control/`, `savings/` elke 30s
- Cumulatieve kWh via `historical_data/` met `deltaMeter` operator, optellen sinds
  een baseline-datum die persistent in HA wordt opgeslagen
- Tokens worden automatisch ververst bij 401-fouten

## Beperkingen

- **Alleen lezen**: geen besturing van de laadpaal mogelijk vanuit HA (zou vereisen
  dat we `powerconnect_control/` POST endpoints reverse-engineeren).
- **Cloud-polling**: data is ~30s vertraagd; korte events worden gemist.
- **Single account**: één instance per Alva-account.

## Licentie

MIT — zie [LICENSE](LICENSE).
