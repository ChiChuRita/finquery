| arm | n | placed | placed and correct | placed and wrong | correct at any confidence | subcategory right |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A model only (all) | 72 | 70/72 (97%) | 69/72 (96%) | 1 | 71/72 (99%) | 54/56 (96%) |
| A model only (chain) | 48 | 48/48 (100%) | 47/48 (98%) | 1 | 47/48 (98%) | 35/37 (95%) |
| A model only (local) | 24 | 22/24 (92%) | 22/24 (92%) | 0 | 24/24 (100%) | 19/19 (100%) |
| B lookup then model (all) | 72 | 69/72 (96%) | 69/72 (96%) | 0 | 71/72 (99%) | 54/56 (96%) |
| B lookup then model (chain) | 48 | 48/48 (100%) | 48/48 (100%) | 0 | 48/48 (100%) | 36/37 (97%) |
| B lookup then model (local) | 24 | 21/24 (88%) | 21/24 (88%) | 0 | 23/24 (96%) | 18/19 (95%) |
| B2 lookup (legal-form rule) then model (all) | 72 | 69/72 (96%) | 68/72 (94%) | 1 | 70/72 (97%) | 54/56 (96%) |
| B2 lookup (legal-form rule) then model (chain) | 48 | 48/48 (100%) | 47/48 (98%) | 1 | 47/48 (98%) | 36/37 (97%) |
| B2 lookup (legal-form rule) then model (local) | 24 | 21/24 (88%) | 21/24 (88%) | 0 | 23/24 (96%) | 18/19 (95%) |
| C model with brief (all) | 72 | 70/72 (97%) | 68/72 (94%) | 2 | 70/72 (97%) | 55/56 (98%) |
| C model with brief (chain) | 48 | 48/48 (100%) | 46/48 (96%) | 2 | 46/48 (96%) | 36/37 (97%) |
| C model with brief (local) | 24 | 22/24 (92%) | 22/24 (92%) | 0 | 24/24 (100%) | 19/19 (100%) |
| lookup alone (today's rule) (all) | 72 | 43/72 (60%) | 43/72 (60%) | 0 | 43/72 (60%) | 34/35 (97%) |
| lookup alone (today's rule) (chain) | 48 | 28/48 (58%) | 28/48 (58%) | 0 | 28/48 (58%) | 22/22 (100%) |
| lookup alone (today's rule) (local) | 24 | 15/24 (62%) | 15/24 (62%) | 0 | 15/24 (62%) | 12/13 (92%) |
| lookup alone (legal-form rule) (all) | 72 | 64/72 (89%) | 63/72 (88%) | 1 | 63/72 (88%) | 49/51 (96%) |
| lookup alone (legal-form rule) (chain) | 48 | 47/48 (98%) | 46/48 (96%) | 1 | 46/48 (96%) | 35/36 (97%) |
| lookup alone (legal-form rule) (local) | 24 | 17/24 (71%) | 17/24 (71%) | 0 | 17/24 (71%) | 14/15 (93%) |

Lookups: 41 ran, 28 refused by the person rule (PayPal Europe S.a.r.l., PayPal Europe S.a.r.l., Metzgerei Huber, Five Guys Germany GmbH, Coffee Fellows GmbH, Espresso House Germany GmbH, Sixt GmbH & Co Autovermietung KG, MILES Mobility GmbH, TIER Mobility SE, JET Tankstellen Deutschland GmbH, Deutsche Tamoil GmbH, Parfuemerie Douglas GmbH, POCO Einrichtungsmaerkte GmbH, About You SE, Fressnapf Tiernahrungs GmbH, Conrad Electronic SE, Blumen Riedel, Sky Deutschland Fernsehen GmbH, Apollo-Optik Holding GmbH, Kieser Training AG, Physiotherapie Am Park, Debeka Krankenversicherungsverein a.G., ERGO Versicherung AG, CinemaxX Entertainment GmbH, Tierpark Berlin-Friedrichsfelde GmbH, Jochen Schweizer GmbH, Scalable Capital GmbH, VHS Berlin Mitte); with the legal-form rule 7 stay refused (PayPal Europe S.a.r.l., PayPal Europe S.a.r.l., Metzgerei Huber, Blumen Riedel, Physiotherapie Am Park, Debeka Krankenversicherungsverein a.G., VHS Berlin Mitte). 0 of 41 lookups fetched a page, mean 3.5 s per lookup, 66 model calls for the lookups against 3 for arm A.
Model: 109 requests, 171774 in, 22826 out, about 0.214 USD.

| merchant | tier | truth | A model | B lookup then model | B2 legal-form rule | C model with brief | lookup queries / fetches |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Hausverwaltung Bergmann GmbH | local | Housing > Rent | Housing > Rent 0.85 ok | Housing > Rent 0.95 ok [lookup] | Housing > Rent 0.95 ok [lookup] | Housing > Rent 0.85 ok | (cache) German property management company (Hausverwaltung) managing |
| Mustermann Systems GmbH | local | Income > Salary | Income > Salary 0.90 ok | Shopping > Electronics 0.20 WRONG [lookup] | Shopping > Electronics 0.20 WRONG [lookup] | Income > Salary 0.90 ok | (cache) Likely a placeholder/test merchant or IT/electronics systems |
| PayPal Europe S.a.r.l. | local | Transfers > Friends and family | Transfers > Friends and family 0.40 ok | Transfers > Friends and family 0.40 ok [model] | Transfers > Friends and family 0.40 ok [model] | Transfers > Friends and family 0.40 ok | refused |
| PayPal Europe S.a.r.l. | local | Transfers > Friends and family | Transfers > Friends and family 0.40 ok | Transfers > Friends and family 0.40 ok [model] | Transfers > Friends and family 0.40 ok [model] | Transfers > Friends and family 0.40 ok | refused |
| Combi Verbrauchermarkt | local | Groceries > Supermarket | Groceries > Supermarket 0.95 ok | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok | combi verbrauchermarkt |
| HIT Handelsgruppe | local | Groceries > Supermarket | Groceries > Supermarket 0.95 ok | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok | hit handelsgruppe was ist |
| nahkauf Kraemer | local | Groceries > Supermarket | Groceries > Supermarket 0.95 ok | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok |  |
| Brezelbaeckerei Ditsch GmbH | local | Groceries > Bakery | Groceries > Bakery 0.90 ok | Groceries > Bakery 0.95 ok [lookup] | Groceries > Bakery 0.95 ok [lookup] | Groceries > Bakery 0.95 ok |  |
| BackFactory GmbH | chain | Groceries > Bakery | Groceries > Bakery 0.90 ok | Groceries > Bakery 0.90 ok [lookup] | Groceries > Bakery 0.90 ok [lookup] | Groceries > Bakery 0.95 ok | backfactory |
| BUDNI Handels- und Service GmbH | local | Groceries > Drugstore | Groceries > Drugstore 0.95 ok | Groceries > Drugstore 0.95 ok [lookup] | Groceries > Drugstore 0.95 ok [lookup] | Groceries > Drugstore 0.95 ok | budni service |
| Flaschenpost SE | chain | Groceries > Supermarket | Groceries > Supermarket 0.90 ok | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.90 ok | flaschenpost de |
| HelloFresh Deutschland SE | chain | Dining/Groceries | Groceries > Supermarket 0.90 ok | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.95 ok [lookup] | Groceries > Supermarket 0.90 ok |  |
| Metzgerei Huber | local | Groceries | Groceries > Supermarket 0.85 ok | Groceries > Supermarket 0.85 ok [model] | Groceries > Supermarket 0.85 ok [model] | Groceries > Supermarket 0.90 ok | refused |
| NORDSEE GmbH | chain | Dining | Dining > Takeaway 0.90 ok | Dining > Takeaway 0.95 ok [lookup] | Dining > Takeaway 0.95 ok [lookup] | Dining > Takeaway 0.90 ok | (cache) German seafood fast-food and quick-service restaurant chain  |
| Block House Restaurantbetriebe AG | chain | Dining > Restaurant | Dining > Restaurant 0.95 ok | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok |  |
| Five Guys Germany GmbH | chain | Dining > Takeaway | Dining > Restaurant 0.95 ok | Dining > Restaurant 0.95 ok [model] | Dining > Takeaway 0.95 ok [lookup] | Dining > Restaurant 0.95 ok | (refused today) what is five guys |
| Coffee Fellows GmbH | chain | Dining > Cafe | Dining > Cafe 0.95 ok | Dining > Cafe 0.95 ok [model] | Dining > Cafe 0.95 ok [lookup] | Dining > Cafe 0.95 ok | (refused today) coffee fellows cafe |
| Espresso House Germany GmbH | chain | Dining > Cafe | Dining > Cafe 0.95 ok | Dining > Cafe 0.95 ok [model] | Dining > Cafe 0.95 ok [lookup] | Dining > Cafe 0.95 ok | (refused today) espresso house |
| Sausalitos Holding GmbH | chain | Dining > Restaurant | Dining > Restaurant 0.95 ok | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok | sausalitos |
| Peter Pane Burgergrill | local | Dining > Restaurant | Dining > Restaurant 0.95 ok | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok [lookup] | Dining > Restaurant 0.95 ok | peter pane burgergrill |
| Sixt GmbH & Co Autovermietung KG | chain | Transport > Car | Transport > Car 0.95 ok | Transport > Car 0.95 ok [model] | Transport > Car 0.99 ok [lookup] | Transport > Car 0.95 ok | (refused today)  |
| MILES Mobility GmbH | chain | Transport | Transport > Car 0.90 ok | Transport > Car 0.95 ok [model] | Transport > Car 0.95 ok [lookup] | Transport > Car 0.95 ok | (refused today) miles mobility |
| TIER Mobility SE | chain | Transport | Transport > Public transport 0.90 ok | Transport > Public transport 0.90 ok [model] | Transport > Public transport 0.95 ok [lookup] | Transport > Public transport 0.90 ok | (refused today) tier mobility |
| FlixTrain GmbH | chain | Transport > Public transport | Transport > Public transport 0.95 ok | Transport > Public transport 0.95 ok [lookup] | Transport > Public transport 0.95 ok [lookup] | Transport > Public transport 0.95 ok |  |
| JET Tankstellen Deutschland GmbH | chain | Transport > Fuel | Transport > Fuel 0.95 ok | Transport > Fuel 0.95 ok [model] | Transport > Fuel 0.95 ok [lookup] | Transport > Fuel 0.95 ok | (refused today) jet tankstellen |
| Deutsche Tamoil GmbH | local | Transport > Fuel | Transport > Fuel 0.95 ok | Transport > Fuel 0.95 ok [model] | Transport > Fuel 0.95 ok [lookup] | Transport > Fuel 0.95 ok | (refused today) deutsche tamoil |
| ADAC e.V. | chain | Insurance/Transport | Transport > Car 0.95 ok | Transport > Car 0.95 ok [lookup] | Transport > Car 0.95 ok [lookup] | Transport > Car 0.90 ok |  |
| TEDi GmbH & Co. KG | chain | Shopping > Home | Shopping > Home 0.85 ok | Shopping > Home 0.95 ok [lookup] | Shopping > Home 0.95 ok [lookup] | Shopping > Home 0.85 ok | tedi shop deutschland |
| Action Deutschland GmbH | chain | Shopping > Home | Shopping > Home 0.85 ok | Shopping > Home 0.90 ok [lookup] | Shopping > Home 0.90 ok [lookup] | Shopping > Home 0.85 ok | action geschaeft deutschland; action markt deutschland |
| KiK Textilien und Non-Food GmbH | chain | Shopping > Clothing | Shopping > Clothing 0.95 ok | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.90 ok |  |
| Deichmann SE | chain | Shopping > Clothing | Shopping > Clothing 0.95 ok | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok | deichmann |
| Parfuemerie Douglas GmbH | chain | Shopping | Shopping 0.85 ok | Shopping 0.90 ok [model] | Groceries > Drugstore 0.95 WRONG [lookup] | Groceries > Drugstore 0.85 WRONG | (refused today)  |
| Snipes SE | chain | Shopping > Clothing | Shopping > Clothing 0.95 ok | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok | snipes shop germany |
| Intersport Deutschland eG | chain | Shopping > Clothing | Shopping > Clothing 0.90 ok | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.85 ok |  |
| toom Baumarkt GmbH | chain | Shopping > Home | Shopping > Home 0.95 ok | Shopping > Home 0.95 ok [lookup] | Shopping > Home 0.95 ok [lookup] | Shopping > Home 0.95 ok |  |
| POCO Einrichtungsmaerkte GmbH | chain | Shopping > Home | Shopping > Home 0.95 ok | Shopping > Home 0.90 ok [model] | Shopping > Home 0.95 ok [lookup] | Shopping > Home 0.95 ok | (refused today)  |
| About You SE | chain | Shopping > Clothing | Shopping > Clothing 0.95 ok | Shopping > Clothing 0.95 ok [model] | Shopping > Clothing 0.95 ok [lookup] | Shopping > Clothing 0.95 ok | (refused today)  |
| Temu | chain | Shopping > Online marketplace | Shopping > Online marketplace 0.95 ok | Shopping > Online marketplace 0.95 ok [lookup] | Shopping > Online marketplace 0.95 ok [lookup] | Shopping > Online marketplace 0.90 ok |  |
| Fressnapf Tiernahrungs GmbH | chain | Shopping | Leisure > Hobbies 0.90 WRONG | Shopping 0.90 ok [model] | Shopping > Home 0.95 ok [lookup] | Leisure > Hobbies 0.85 WRONG | (refused today)  |
| Conrad Electronic SE | chain | Shopping > Electronics | Shopping > Electronics 0.95 ok | Shopping > Electronics 0.95 ok [model] | Shopping > Electronics 0.95 ok [lookup] | Shopping > Electronics 0.95 ok | (refused today)  |
| Hugendubel Digital GmbH | chain | Leisure > Books | Leisure > Books 0.95 ok | Leisure > Books 0.95 ok [lookup] | Leisure > Books 0.95 ok [lookup] | Leisure > Books 0.95 ok | hugendubel digital |
| Blumen Riedel | local | Leisure/Shopping | Shopping > Home 0.90 ok | Shopping > Home 0.80 ok [model] | Shopping > Home 0.80 ok [model] | Shopping > Home 0.85 ok | refused |
| Sky Deutschland Fernsehen GmbH | chain | Subscriptions > Streaming | Subscriptions > Streaming 0.95 ok | Subscriptions > Streaming 0.95 ok [model] | Subscriptions > Streaming 0.95 ok [lookup] | Subscriptions > Streaming 0.95 ok | (refused today)  |
| Deezer SA | chain | Subscriptions > Music | Subscriptions > Music 0.95 ok | Subscriptions > Music 0.95 ok [lookup] | Subscriptions > Music 0.95 ok [lookup] | Subscriptions > Music 0.95 ok | what is deezer |
| Xbox Game Pass | chain | Leisure/Subscriptions | Leisure > Hobbies 0.90 ok | Subscriptions > Software 0.95 ok [lookup] | Subscriptions > Software 0.95 ok [lookup] | Leisure > Hobbies 0.85 ok |  |
| Duolingo Inc | chain | Education/Subscriptions | Education > Courses 0.90 ok | Education > Courses 0.95 ok [lookup] | Education > Courses 0.95 ok [lookup] | Education > Courses 0.90 ok |  |
| Zeit Online GmbH | local | Subscriptions > News | Subscriptions > News 0.95 ok | Subscriptions > News 0.95 ok [lookup] | Subscriptions > News 0.95 ok [lookup] | Subscriptions > News 0.95 ok | zeit verlag abo kreditkarte |
| clever fit GmbH | chain | Health > Fitness | Health > Fitness 0.95 ok | Health > Fitness 0.95 ok [lookup] | Health > Fitness 0.95 ok [lookup] | Health > Fitness 0.95 ok | what is clever fit germany |
| FitX Deutschland GmbH | chain | Health > Fitness | Health > Fitness 0.95 ok | Health > Fitness 0.95 ok [lookup] | Health > Fitness 0.95 ok [lookup] | Health > Fitness 0.95 ok | fitx deutschland unternehmen |
| Apollo-Optik Holding GmbH | chain | Health | Health 0.85 ok | Health 0.90 ok [model] | Health 0.95 ok [lookup] | Health 0.85 ok | (refused today) apollo optik |
| Kieser Training AG | chain | Health > Fitness | Health > Fitness 0.95 ok | Health > Fitness 0.95 ok [model] | Health > Fitness 0.95 ok [lookup] | Health > Fitness 0.95 ok | (refused today) kieser training |
| Physiotherapie Am Park | local | Health > Doctor | Health > Doctor 0.90 ok | Health > Doctor 0.85 ok [model] | Health > Doctor 0.85 ok [model] | Health > Doctor 0.90 ok | refused |
| Debeka Krankenversicherungsverein a.G. | chain | Insurance > Health insurance | Insurance > Health insurance 0.95 ok | Insurance > Health insurance 0.95 ok [model] | Insurance > Health insurance 0.95 ok [model] | Insurance > Health insurance 0.95 ok | refused |
| ERGO Versicherung AG | chain | Insurance > Liability | Insurance > Liability 0.95 ok | Insurance > Liability 0.95 ok [model] | Insurance 0.95 ok [lookup] | Insurance > Liability 0.95 ok | (refused today)  |
| BARMER | chain | Insurance > Health insurance | Insurance > Health insurance 0.95 ok | Insurance > Health insurance 0.95 ok [lookup] | Insurance > Health insurance 0.95 ok [lookup] | Insurance > Health insurance 0.95 ok | barmer krankenkasse |
| E.ON Energie Deutschland GmbH | local | Housing > Electricity | Housing > Electricity 0.95 ok | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok | on energie deutschland |
| Yello Strom GmbH | chain | Housing > Electricity | Housing > Electricity 0.95 ok | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok | yello strom |
| Octopus Energy Germany GmbH | chain | Housing > Electricity | Housing > Electricity 0.95 ok | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok [lookup] | Housing > Electricity 0.95 ok | octopus energy germany strom |
| 1&1 Telecom GmbH | local | Communication/Housing | Housing > Internet 0.90 ok | Communication > Mobile 0.85 ok [lookup] | Communication > Mobile 0.85 ok [lookup] | Housing > Internet 0.90 ok | telecom germany telecommunication |
| freenet DLS GmbH | local | Communication > Mobile | Communication > Mobile 0.95 ok | Communication > Mobile 0.95 ok [lookup] | Communication > Mobile 0.95 ok [lookup] | Communication > Mobile 0.90 ok | freenet dls gmbh |
| CinemaxX Entertainment GmbH | chain | Leisure > Events | Leisure > Events 0.95 ok | Leisure > Events 0.95 ok [model] | Leisure > Events 0.95 ok [lookup] | Leisure > Events 0.95 ok | (refused today) cinemaxx entertainment |
| Tierpark Berlin-Friedrichsfelde GmbH | local | Leisure > Events | Leisure > Events 0.90 ok | Leisure > Events 0.90 ok [model] | Leisure > Events 0.95 ok [lookup] | Leisure > Events 0.90 ok | (refused today) tierpark friedrichsfelde |
| Jochen Schweizer GmbH | chain | Leisure > Events | Leisure > Hobbies 0.85 ok | Leisure > Events 0.90 ok [model] | Leisure > Events 0.95 ok [lookup] | Leisure > Events 0.85 ok | (refused today) jochen schweizer unternehmen |
| Karls Markt OHG | local | Groceries/Leisure | Leisure > Events 0.85 ok | Leisure > Events 0.85 ok [lookup] | Leisure > Events 0.85 ok [lookup] | Leisure > Events 0.90 ok | karls deutschland unternehmen |
| ARD ZDF Deutschlandradio Beitragsservice | chain | Fees and taxes/Housing/Subscriptions | Subscriptions 0.85 ok | Fees and taxes > Taxes 0.95 ok [lookup] | Fees and taxes > Taxes 0.95 ok [lookup] | Fees and taxes > Taxes 0.90 ok |  |
| Finanzamt Berlin Mitte/Tiergarten | local | Fees and taxes > Taxes | Fees and taxes > Taxes 0.95 ok | Fees and taxes > Taxes 0.99 ok [lookup] | Fees and taxes > Taxes 0.99 ok [lookup] | Fees and taxes > Taxes 0.95 ok |  |
| Landeshauptkasse Berlin | local | Fees and taxes | Fees and taxes 0.85 ok | Fees and taxes > Taxes 0.85 ok [lookup] | Fees and taxes > Taxes 0.85 ok [lookup] | Fees and taxes 0.80 ok | was ist landeshauptkasse |
| Trade Republic Bank GmbH | chain | Transfers > Savings | Transfers > Savings 0.90 ok | Transfers > Savings 0.95 ok [lookup] | Transfers > Savings 0.95 ok [lookup] | Transfers > Savings 0.95 ok |  |
| Scalable Capital GmbH | chain | Transfers > Savings | Transfers > Savings 0.90 ok | Transfers > Savings 0.95 ok [model] | Transfers > Savings 0.95 ok [lookup] | Transfers > Savings 0.95 ok | (refused today) scalable capital was ist das |
| Bundesagentur fuer Arbeit | chain | Income > Other income | Income > Other income 0.95 ok | Income > Other income 0.95 ok [lookup] | Income > Other income 0.95 ok [lookup] | Income > Other income 0.95 ok |  |
| Fahrschule Mobil GmbH | local | Education > Courses | Education > Courses 0.90 ok | Education > Courses 0.95 ok [lookup] | Education > Courses 0.95 ok [lookup] | Education > Courses 0.90 ok |  |
| VHS Berlin Mitte | local | Education > Courses | Education > Courses 0.95 ok | Education > Courses 0.95 ok [model] | Education > Courses 0.95 ok [model] | Education > Courses 0.95 ok | refused |
