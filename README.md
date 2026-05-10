# Alva Charging — Home Assistant integration

> # 🛑 STOP — niet voor jou bedoeld
>
> Deze repo bestaat alleen omdat het de simpelste manier is om de integratie
> via HACS aan één specifieke Home Assistant te leveren (die van mijn
> schoonouders). Hij is **niet** bedoeld als breed publiek project.
>
> - Geen support, geen issues, geen PRs.
> - Reverse-engineered tegen een ongedocumenteerde Scoptvision-API; kan op
>   elk moment kapot gaan.
> - Geen test-coverage. Bouw mee gemaakt met [Claude Code](https://claude.com/code).
> - Account-specifieke aannames (single-connector Alfen Eve, Nederlandse
>   tijdzone, één gebruiker per HA).
>
> **Als je hier per ongeluk bent**: scroll terug en kijk eens naar
> [`alfen_wallbox`](https://github.com/leeyuentuen/alfen_wallbox) of
> [`evcc`](https://github.com/evcc-io/evcc) — dat zijn echte projecten met
> een gemeenschap.

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

## Voorbeeld-Lovelace

Plak dit als een `vertical-stack` (of stuk daarvan) in je dashboard:

```yaml
type: vertical-stack
cards:
  - type: glance
    title: Alva laadpaal
    columns: 4
    entities:
      - entity: select.alva_charging_laadmodus_instellen
        name: Modus
      - entity: sensor.alva_charging_laadstatus
        name: Status
      - entity: binary_sensor.alva_charging_aan_het_laden
        name: Laadt
      - entity: binary_sensor.alva_charging_auto_verbonden
        name: Auto

  - type: entities
    title: Live
    entities:
      - sensor.alva_charging_laadvermogen
      - sensor.alva_charging_netvermogen
      - sensor.alva_charging_huidig_laad_doel
      - sensor.alva_charging_laadbehoefte
      - sensor.alva_charging_laden_klaar_voor

  - type: statistic
    title: Geladen vandaag
    entity: sensor.alva_charging_geladen_totaal_vandaag
    stat_type: change
    period:
      calendar:
        period: day

  - type: gauge
    name: Zonpercentage deze maand
    entity: sensor.alva_charging_zonpercentage_deze_maand
    min: 0
    max: 100
    severity:
      green: 80
      yellow: 50
      red: 0

  - type: calendar
    entities:
      - calendar.alva_charging_laadschema
    initial_view: listWeek
```

## Licentie

MIT — zie [LICENSE](LICENSE).
