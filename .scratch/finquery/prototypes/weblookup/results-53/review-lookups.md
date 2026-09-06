| merchant | token | steps | queries | fetched | conclusion | conf | s | model calls |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| LIDL Vertriebs GmbH | `lidl` | cache | - | - | Groceries > Supermarket | 0.95 | 0.0 | 0 |
| dm drogerie markt | `dm drogerie` | cache | - | - | Groceries > Drugstore | 0.95 | 0.0 | 0 |
| NETTO MARKEN-DISCOUNT | `netto marken discount` | cache | - | - | Groceries > Supermarket | 1.00 | 0.0 | 0 |
| Lieferando.de | `lieferando` | cache | - | - | Dining > Delivery | 0.80 | 0.0 | 0 |
| DEAN AND DAVID | `dean david` | cache | - | - | Dining > Takeaway | 0.70 | 0.0 | 0 |
| Döner Haus Kreuzberg | `doener haus kreuzberg` | cache | - | - | Dining > Restaurant | 0.80 | 0.0 | 0 |
| Cafe Milchbart | `cafe milchbart` | cache | - | - | Dining > Cafe | 0.85 | 0.0 | 0 |
| VAPIANO Berlin Mitte | `vapiano mitte` | cache | - | - | Dining > Restaurant | 0.60 | 0.0 | 0 |
| UBER BV | `uber` | cache | - | - | Transport > Ride hailing | 0.60 | 0.0 | 0 |
| SHELL DEUTSCHLAND | `shell` | cache | - | - | Transport > Fuel | 0.60 | 0.0 | 0 |
| Telekom Deutschland GmbH | `telekom` | cache | - | - | Communication > Mobile | 0.95 | 0.0 | 0 |
| ADOBE SYSTEMS SOFTWARE | `adobe systems software` | cache | - | - | Subscriptions > Software | 0.60 | 0.0 | 0 |
| BVG Berliner Verkehrsbetriebe | `bvg berliner verkehrsbetriebe` | cache | - | - | Transport > Public transport | 0.60 | 0.0 | 0 |
| Vattenfall Europe Sales GmbH | `vattenfall sales` | 1 search, 1 fetch | what is vattenfall sales; what is vattenfall sales | en.wikipedia.org/wiki/Vattenfall | Housing > Electricity | 0.95 | 10.3 | 4 |
| Allianz Versicherungs-AG | `allianz versicherungs` | 1 search, 1 fetch | allianz versicherungs was ist | de.wikipedia.org/wiki/Allianz_SE | Insurance | 0.90 | 11.2 | 3 |
| Sparkasse Geldautomat | `sparkasse geldautomat` | 1 search, 1 fetch | what is sparkasse geldautomat | de.wikipedia.org/wiki/Geldautomat | Cash > Cash withdrawal | 0.90 | 7.5 | 3 |
| Hausverwaltung Bergmann GmbH | `hausverwaltung bergmann` | 3 search, 0 fetch | was ist hausverwaltung bergmann; was ist hausverwaltung bergmann; Unternehmen hausverwaltung bergmann; Firma hausverwaltung bergmann | - | Housing > Rent | 0.60 | 38.3 | 7 |
| Mustermann Systems GmbH | `mustermann systems` | 2 search, 0 fetch | mustermann systems Firma; mustermann systems Firma; mustermann systems | - | Shopping > Electronics | 0.60 | 8.9 | 4 |
| Zahnarztpraxis Dr. Lorenz | `zahnarztpraxis dr lorenz` | 2 search, 1 fetch | zahnarztpraxis dr lorenz; zahnarztpraxis dr lorenz; Unternehmen zahnarztpraxis dr lorenz | www.zahnarzt-lorenz.de/ | Health > Doctor | 0.95 | 14.6 | 6 |
| Apotheke am Markt | `apotheke` | 2 search, 1 fetch | apotheke; apotheke Unternehmen; apotheke Unternehmen | de.wikipedia.org/wiki/Apotheke | Health > Pharmacy | 0.95 | 10.7 | 4 |
| PayPal Europe S.a.r.l. | `` | refused | - | - | - | 0.00 | 0.0 | 0 |

21 strings, 7 lookups ran, 5 of them fetched a page, mean 14.5 s, model requests 31, tokens in 84208 out 10778, about 0.104 USD.
