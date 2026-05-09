# Alva Charging — installatie in Home Assistant

Een custom component die de Alva Charging cloud (Scoptvision API) uitleest en de
laadpaaldata blootlegt als sensors in Home Assistant.

## Wat krijg je?

**Sensors:**
- `sensor.alva_charging_laadvermogen` — actueel laadvermogen (W)
- `sensor.alva_charging_totaal_geladen` — cumulatieve geladen energie (kWh, `total_increasing`) — voor Energy Dashboard
- `sensor.alva_charging_netvermogen` — actueel netvermogen (W)
- `sensor.alva_charging_laadstatus` — charging / paused / idle
- `sensor.alva_charging_laadmodus` — solar / autopilot / boost
- `sensor.alva_charging_laadbehoefte` — gewenste range (km)
- `sensor.alva_charging_maandpiek` — piekvermogen deze maand (W)
- `sensor.alva_charging_sessie_gestart` — starttijd huidige sessie
- `sensor.alva_charging_zon_besparing` — besparing door zon laden (EUR)

**Binary sensors:**
- `binary_sensor.alva_charging_auto_verbonden`
- `binary_sensor.alva_charging_laadpaal_online`
- `binary_sensor.alva_charging_aan_het_laden`

## Installatie via File editor

1. Open Home Assistant in de browser
2. Installeer de **File editor** add-on (Instellingen → Add-ons → Add-on store) als je die nog niet hebt
3. Open File editor en navigeer naar `/config/`
4. Maak de map `custom_components/alva_charging/` aan (en de submap `translations/`)
5. Upload of plak de volgende bestanden in `/config/custom_components/alva_charging/`:
   - `__init__.py`
   - `manifest.json`
   - `const.py`
   - `api.py`
   - `coordinator.py`
   - `config_flow.py`
   - `entity.py`
   - `sensor.py`
   - `binary_sensor.py`
   - `strings.json`
   - `translations/nl.json`
6. **Herstart Home Assistant** (Instellingen → Systeem → rechtsboven herstartknop)
7. Ga na herstart naar **Instellingen → Apparaten en services → Integratie toevoegen**
8. Zoek naar **"Alva Charging"** en vul je e-mailadres + wachtwoord van
   `slimladen.alva-charging.nl` in
9. Klaar — de sensors verschijnen onder een nieuw apparaat "Alva Charging"

## Energy Dashboard koppelen

De integratie levert direct een `total_increasing` kWh-sensor die geschikt is
voor het Energy Dashboard. Geen Riemann-sum helper nodig.

**Hoe het werkt:** bij installatie wordt de huidige UTC-tijd opgeslagen als
"baseline". Elke 2 minuten haalt de coordinator alle uur-delta's op via
`historical_data/` vanaf die baseline tot nu, en telt ze op. Dat geeft een
waarde die alleen omhoog gaat — en die overleeft HA-restarts en cloud-outages
omdat het bij elke poll de hele periode opnieuw uitleest.

1. Ga naar **Instellingen → Dashboards → Energie**
2. Onder **"Individuele apparaten"** → **"Apparaat toevoegen"**
3. Selecteer `sensor.alva_charging_totaal_geladen`

> **Let op:** de eerste meting toont 0 kWh. Pas wanneer er na installatie
> daadwerkelijk geladen wordt, gaat de waarde omhoog. Eerder geladen energie
> (van vóór de installatie van de integratie) wordt niet meegeteld.

## Updaten

Vervang de bestanden in `/config/custom_components/alva_charging/` en herstart HA.

## Troubleshooting

**"Ongeldige inloggegevens"** — controleer dat de e-mail en wachtwoord werken op
slimladen.alva-charging.nl in de browser.

**"Kan geen verbinding maken"** — check de logs (Instellingen → Systeem → Logboeken)
voor `alva_charging`. Meestal duidt dit op een verlopen API-key of een rate
limit.

**Sensors blijven `unavailable`** — herstart de integratie (Apparaten en services →
Alva Charging → 3-puntsmenu → Herladen).

## Beperkingen

- **Cloud-polling**: data komt elke 30s binnen; kortere events worden gemist.
- **Geen besturing**: alleen lezen (geen modus switchen vanuit HA). Kan later worden
  toegevoegd.
- **Pioniersversie**: dit is reverse-engineered; Alva/Scoptvision kan de API zonder
  waarschuwing veranderen.
