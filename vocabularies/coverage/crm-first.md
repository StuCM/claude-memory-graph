# CRM-first: where each phrasing lives

Moved: promotable (and promotable on a longer path) phrasings the gate accepted, and copies of phrasings the ontology layer already gave; each is now in phrases.json only. Every other phrasing stays in its layer with the reason below.

| layer | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | gate-rejected | not applied | already in ontology |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 846 | 628 | 3326 | 2 | 799 | 791 | 962 | 4 | 147 |
| client | 1 | 0 | 18 | 0 | 34 | 3 | 0 | 0 | 1 |

## Per graph

| layer | graph | promotable | promotable longer path | ambiguous path | non-CRM | site-specific | clash | gate-rejected | not applied | already in ontology |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | Activity | 31 | 40 | 215 | 0 | 93 | 21 | 50 | 0 | 9 |
| base | Application Area | 32 | 21 | 183 | 0 | 1 | 35 | 20 | 0 | 0 |
| base | Area | 82 | 60 | 282 | 0 | 122 | 82 | 83 | 0 | 20 |
| base | Artefact | 56 | 57 | 227 | 0 | 36 | 90 | 92 | 1 | 28 |
| base | Bibliographic Source | 9 | 13 | 122 | 0 | 0 | 23 | 34 | 0 | 1 |
| base | Consultation | 96 | 26 | 327 | 0 | 32 | 37 | 63 | 0 | 1 |
| base | Digital Object | 15 | 11 | 80 | 0 | 0 | 41 | 22 | 0 | 1 |
| base | Heritage Story | 34 | 38 | 142 | 0 | 61 | 46 | 73 | 0 | 6 |
| base | Historic Aircraft | 118 | 75 | 328 | 0 | 132 | 92 | 112 | 0 | 11 |
| base | Historic Landscape Characterization | 48 | 37 | 189 | 0 | 0 | 49 | 40 | 0 | 3 |
| base | Maritime Vessel | 140 | 76 | 306 | 0 | 111 | 56 | 96 | 0 | 15 |
| base | Monument | 90 | 90 | 329 | 2 | 180 | 108 | 146 | 2 | 25 |
| base | Organization | 36 | 29 | 120 | 0 | 1 | 38 | 27 | 0 | 10 |
| base | Period | 18 | 12 | 116 | 0 | 0 | 22 | 29 | 0 | 1 |
| base | Person | 34 | 31 | 203 | 0 | 29 | 43 | 58 | 1 | 13 |
| base | Place | 7 | 12 | 157 | 0 | 1 | 8 | 17 | 0 | 3 |
| client | Figure | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| client | Monument | 0 | 0 | 6 | 0 | 34 | 1 | 0 | 0 | 0 |
| client | Object | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| client | Tale | 1 | 0 | 6 | 0 | 0 | 1 | 0 | 0 | 1 |

## Gate: 152 of 223 accepted

| kind | path | phrases | verdict |
| --- | --- | --- | --- |
| field | E18 P53 E53 P1 E41 P3 | address of the site | bench: adds no right answer |
| date | E53 P140i E13 P141 | area status date, area status since, status since, status dates, status assigned, area status from, in the area since, when was the status given, when was the area status assigned | accepted |
| link | E18 P12i | archaeological investigations, watching brief | accepted |
| link | P16 E24 P49 | archive held by, who holds the archive, where is the archive, archive repository, records held by, holds archive, hold archive, who holds archive, archive location, where are the records kept, archive object held by, holder of archive object | bench: worse on 2, e.g. her: which activities have Brynquorn as archive location? |
| field | P16 E24 P1 E41 P3 | archive, archive title, archive item, archive object, archive material, archives, archive object title, archive items | bench, together: catalina: what is the image of Talquorn? |
| field | P16 E24 P1 E42 P3 | archive reference, archive number, archive accession number, archive object reference, accession number | accepted |
| link | E18 P16i | planning application, planning history | accepted |
| link | E18 P140i E13 P140 | nearby monuments, linked sites, related finds, related records | accepted |
| property | E18 P140i E13 P2 | relationship type, how are they related, nature of link | demo bank worse: refused-should-answer -> wrong: what is related to Navan Fort? | Show the association type of Monument 'Navan Fort, Navan'. | 1 |  |
| field | D1 P67i E33 P3 | audit note, audit notes, record notes, editorial note, administrative notes, editorial notes, record keeping note | accepted |
| property | P67i D1 P2 | validation, validation status, record checked, quality check, needs work, record status, checked ok, possible duplicate, has the record been checked | bench: worse on 1, e.g. her: what is the record status of Keldrith? |
| field | E73 P129i E33 P3 | source comment, citation note, citation comment, note on source, source notes | bench: adds no right answer |
| field | E73 P1 E42 P3 | source number, citation number, source reference number | bench: adds no right answer |
| property | P31 E24 P45 | component material, material of components, material of the parts, fittings material, element materials, features made of | accepted |
| property | P31 E24 P2 | components, component, parts, architectural features, features, elements, fixtures, fittings, architectural elements, what features, component type | bench: worse on 1, e.g. her: what is the component of Mavdrith? |
| property | O18i E11 P32 | component construction technique, how were the parts made, component technique, technique of components | accepted |
| property | E11 P140i E13 P32 | component evidence, evidence for components, component evidence type | accepted |
| date | O18i E11 P4 | erected, put up, construction, when was it built, year built, built in, building date, date of construction, originally built, first built, how old, age of the building, dated, dates from, construction phase, when was it constructed, laid out, origins | accepted |
| link | O18i E11 P10 | period, what period, which period, era, cultural period, historic period, period of construction, date period, age, epoch, archaeological period, time period, historical period, built in which period, from what period, what era, dates to | accepted |
| property | O18i E11 P2 | phase type, type of phase, construction phase type, building phase, phases, phase, building phases, development phases | accepted |
| field | E11 P4 E52 P3 | display date, date text, approximate date, date range, construction date text, date as written, circa date | bench: worse on 2, e.g. her: what is the display date of Mavdrith? |
| property | E11 P41i E17 P32 | evidence, evidence type, type of evidence, what survives, surviving evidence, form of evidence, remains, what remains, survival, earthwork or cropmark, extant, does it survive, surviving remains, state of remains, how much survives, how is it evidenced | accepted |
| property | E18 O18i E11 P41i E17 P141 | confidence of interpretation, interpretation certainty, how certain is the interpretation, certainty, how sure is the identification, confidence in identification | accepted |
| field | E17 P67i E33 P3 | phase description, description of the phase, phase notes, phase summary, description of phase, phase details, construction notes, classification notes, construction phase description | accepted |
| property | P94i D10 P33 | coordinate system, projection, crs, spatial reference system, osgb36, wgs84 | accepted |
| field | P67 D1 P1 E41 P3 | base map, current base map, base mapping, background map, which base map, basemap | bench: adds no right answer |
| field | E18 P67i E33 P3 | significance statement, notes | bench: adds no right answer |
| link | P140i E17 P12 | designation documents, listing documents, listing description file, list entry document, designation document, designation file, protection document, listing document, designation files | accepted |
| property | P140i E17 P41 | at risk, heritage at risk, risk status, is it at risk, endangered, threatened, state of repair, under threat, risk register, vulnerable, risk, in danger, on the at risk register | accepted |
| field | P141 E41 P3 | designation name, list entry name, listed name, name on the list, scheduled name, name of designation, protection name, protected as, listing name | accepted |
| property | P140i E17 P2 | local list criteria, local heritage list criteria, why locally listed, reasons for local listing, local listing criteria, selection criteria, local heritage criteria, significance criteria, reason for local listing, criteria | accepted |
| field | P140i E17 P3 | list entry link, designation url, listing link, designation link, list entry url, listing url, official list link | bench: adds no right answer |
| property | P1 E42 P71i | cross reference source, reference source, which database, external database, source of reference, source of external reference, source of the cross reference | accepted |
| field | P1 E42 P67i E73 P3 | cross reference note, cross reference notes, external reference note, note on cross reference | bench: adds no right answer |
| field | O7i SP6 P168 | coordinates, geometry, on the map, map, lat long, latitude, longitude, footprint, boundary, extent, polygon, geolocation, map location, spatial extent, gps, latitude and longitude, mapped, location, where is it, position, geographic location, whereabouts on map, mapped extent, spatial location, show on map | bench: worse on 8, e.g. catalina: what is the location of Brynquorn? |
| field | E36 P67i E33 P3 | caption, image caption, photo caption, picture caption | accepted |
| link | E36 P104 E30 P75i | copyright owner, image copyright owned by, photo credit, who owns the copyright, image credit, holds copyright, hold copyright, copyright held by, who holds copyright, image copyright holder, photo copyright owner, image rights holder, who owns the image copyright, image copyright owner, photo copyright holder, rights holder | bench: worse on 3, e.g. her: which artefacts have Brynquorn as copyright owner? |
| property | E36 P104 E30 P2 | copyright, copyright type, licence, license, image licence, rights, reuse rights, creative commons, crown copyright, image copyright, photo copyright, image rights, photo rights, can i use the image, usage rights | accepted |
| field | E36 P104 E30 P67i E33 P3 | copyright note, copyright statement, rights statement, copyright notes, credit line | bench: worse on 1, e.g. catalina: what is the copyright statement of Mavdrith? |
| field | P141 E33 P3 | land use notes, land use note, notes on land use | bench: adds no right answer |
| property | P89 E53 P1 E41 P3 | borough, london borough, district, parish, local authority, council area, administrative area, which borough, which council, county council area, local planning authority, area name, council, local authority area, what borough, which district, local council | accepted |
| field | E18 P1 E41 P3 | monument name, site name, named, building name, what is its name, names, alternative name, former name | accepted |
| link | P89 E53 P89i | named location, place, named place, settlement, which place, place name, located at, place found, find place, findplace, place name of findspot, nearby place | bench: worse on 6, e.g. catalina: what is the kind of place of Talzabel? |
| field | E18 P53 E53 Q11i SP6 P168 | easting, northing, eastings and northings, ordnance survey reference | bench: adds no right answer |
| link | E18 P46i | parent monument, within the complex, part of which site, parent record, component of | accepted |
| date | E18 P140i E13 P141 | radiocarbon dated, carbon-dated, tree-ring date, luminescence date | accepted |
| date | E18 P140i E13 P4 | lab analysis date | accepted |
| property | E18 P140i E13 P32 | carbon dating, tree-ring dating, luminescence, archaeomagnetism | accepted |
| field | P33 E29 P3 | standard deviation, error margin, plus or minus, margin of error, date error, sigma, uncertainty, uncertainty range, uncertainty of date | bench: adds no right answer |
| field | SP6 P129i E33 P3 | spatial notes, mapping notes, geometry notes, spatial metadata | bench: adds no right answer |
| date | SP6 P140i E13 P4 | spatial record authorised, spatial record authorized, date of authorisation, date of authorization, when was the mapping authorised, mapping authorized, location authorised, mapping authorised, geometry authorised, map record authorised, when was the location authorised | accepted |
| property | SP6 P140i E13 P2 | authorisation status, authorization status, mapping approved, spatial authorization, awaiting authorization, is the mapping authorised, authorised location | accepted |
| field | E13 P14 E21 P1 E41 P3 | authorised by, authorized by, authoriser, authorizer, who authorised, spatial record authorised by, mapping authorised by, who authorised the mapping, location authorised by | bench: adds no right answer |
| date | P12i E5 P4 | was in use, used from, used until, occupation, in operation, operated, operational, functioning, inhabited, period of use dates, use dates, when was it used, abandoned, went out of use, disused, period of use, when was it occupied, date of use, use phase | bench: worse on 1, e.g. her: when was Talquorn period of use? |
| link | P12i E5 P10 | period of use, use period, occupation period, period in use, period when used, period of use era, used during period, era of use | accepted |
| property | E5 P41i E17 P42 | what was it used for, what is it used for, original use, current use, role, usage, what did it do, craft type, role of vessel, what was it for | bench: worse on 6, e.g. catalina: what is the what did it do of Brynquorn? |
| field | E5 P41i E17 P67i E73 P3 | use description, how was it used, use history, history of use, description of use, service history, career, operational history, use notes, function notes, use phase description | bench: worse on 4, e.g. catalina: what is the how was it used of Mavquorn? |
| property | E5 P41i E17 P32 | evidence of use, use evidence, evidence for use, use phase evidence | bench: adds no right answer |
| field | P12i E5 P3 | use date text, period of use display date, use display date | bench: adds no right answer |
| link | E33 P67 E7 | activities, associated activities, events, projects, related events, investigations | accepted |
| link | E33 P129 E18 | places in the story, related sites, objects, featured sites, which monuments, places featured, which buildings, places mentioned | bench: worse on 13, e.g. catalina: how many digital objects are part of Ruvzabel? |
| property | E33 P103 | audience, intended audience, who is it for, target audience, suitable for, aimed at, readership, audience type | accepted |
| link | E33 P129i E73 | written about in, documentary sources | accepted |
| link | E33 P67i D1 | media, files, audio, video, documents, attachments, podcast, recording, digital files, multimedia, downloads, digital copy, digital file, pdf, scan, online copy | bench: worse on 4, e.g. her: which consultations have Bryndrith as attachments? |
| field | P67 E53 Q11i SP6 P168 | where, geographic coverage, where is it set, geography, where did it happen, where does it take place | bench: adds no right answer |
| field | E33 P138i | images, image, photos, photo, pictures, picture, photographs, what does it look like, illustrations | bench, together: catalina: what is the image of Talquorn? |
| link | E33 P148i | parent story, series, part of a larger story, main story, chapter of, broader story, belongs to, larger narrative, story collection, come from | accepted |
| link | E33 P67 E4 | when is the story set, temporal coverage, what period does it cover, period covered, when does it take place | accepted |
| link | E33 P73 | translations, translated version, other languages, in another language, language versions, in welsh, in french | accepted |
| link | P8i E13 P140 | associated buildings, works, what did he build, what did she build, what did he design, what did she design, buildings designed, places associated, where did he work, known for building | accepted |
| field | E67 P7 E53 P1 E41 P3 | where was he born, where was she born, where were they born, where born, native of, hometown, home town, came from, birth place, born where | bench: adds no right answer |
| link | P98i E67 P97 | dad, his father, her father, father's name, paternal, who was his father, who was her father, fathered by | accepted |
| link | P98i E67 P96 | mum, mom, his mother, her mother, mother's name, maternal, who was his mother, who was her mother | accepted |
| field | E41 P1 E41 P3 | contact name, correspondence name, name for correspondence, contact person, who to contact, named contact | bench: adds no right answer |
| field | E69 P7 E53 P1 E41 P3 | where did he die, where did she die, where did they die, deathplace, death place, died where, where died | bench: adds no right answer |
| field | E21 P129i E33 P3 | bio, life, who was, life story, achievements, occupation, profession, what did he do, what did she do, known for | bench: worse on 4, e.g. catalina: what is the what did he do of Mavzabel? |
| link | E21 P67i D1 | scans | accepted |
| field | P74 E53 P1 E41 P3 | address, home address, lived at, where did he live, where did she live, where does he live, where does she live, residence, lived, resided, full address, where lived, home, street address, postal address, what is the address, where is it based, headquarters, office, based in, premises, located at | accepted |
| field | P130 E41 P3 | surname, last name, family name, second name | accepted |
| field | E65 P129i E33 P3 | statement of responsibility, responsibility, credits, responsible for | accepted |
| field | E33 P129i E33 P3 | abstract, what is it about, synopsis, contents | bench: adds no right answer |
| link | E33 P106i | journal, serial, periodical, part of series, magazine, which journal, published in journal, journal title, in the series | bench: adds no right answer |
| field | P43 E54 P90 | number of pages, how many pages, page count, length in pages, how long is it | accepted |
| field | E12 P14 E39 P1 E41 P3 | publisher, published by, who published it, publishing house, press | accepted |
| field | E12 P7 E53 P1 E41 P3 | place of publication, where was it published, where published, publication place, city of publication | bench: adds no right answer |
| field | E13 P67i E33 P3 | area reference, area assignment reference, area reference value, area reference note | accepted |
| field | E22 P1 E41 P3 | object name, artefact name, artifact name | accepted |
| link | E22 P12i | excavation project, recovered during, investigation, found during, which excavation, survey | accepted |
| link | E22 P67i | reports on | accepted |
| date | P34i E14 P4 | condition assessment date, when was its condition assessed, inspected, when was it inspected, condition checked | accepted |
| link | P35 E3 P129i | condition report file, condition documents, condition photos | accepted |
| property | P35 E3 P2 | preservation, damaged, how well preserved, condition rating, intact, what condition, broken | accepted |
| field | S19 P129i E33 P3 | discovery notes, circumstances of discovery, find circumstances, discovery details, how it was discovered, story of the find | bench: adds no right answer |
| field | S19 P14 E21 P1 E41 P3 | found by, finder, discovered by, who found it, who discovered it, detectorist, name of finder | accepted |
| field | P128 E34 P3 | inscription, inscribed, writing, text on it, legend, what does it say, inscribed text, lettering, engraved text, words on it | bench: worse on 4, e.g. catalina: what is the inscribed of Ruvdrith? |
| field | P73 E33 P3 | what does the inscription mean, translated, meaning of inscription, english translation | bench: adds no right answer |
| field | E34 P67i E33 P3 | inscription notes, inscription note, notes on inscription | bench: adds no right answer |
| date | P141i E13 P141 | when was land use assessed | bench: adds no right answer |
| field | P40 E54 P90 | dimensions, size, measurements, how big, measurement, measurement value, measures, how large, measured, dimension | bench: adds no right answer |
| property | P40 E54 P91 | unit, measurement unit, units, measured in, unit of measurement, in metres or feet | accepted |
| field | P7 E53 Q11i SP6 P168 | grid reference, ngr, os grid reference, national grid reference, grid ref, findspot grid reference, os reference | accepted |
| link | P108i E12 P14 | manufacturer, who made it, workshop, craftsman, crafted by, potter, produces, produce, who produces | accepted |
| property | E12 P41i E17 P42 | artefact type, artifact type, what kind, what sort of object, what type, find type, object category | accepted |
| property | P108i E12 P126 | what is it made of, composition, what material, metal, constructed from | accepted |
| property | E12 P41i E17 P141 | confidence, how certain, confidence of identification, how sure | bench: worse on 2, e.g. catalina: what is the how sure of Ruvdrith? |
| field | E12 P41i E17 P67i E73 P3 | production notes, classification description, production description | bench: adds no right answer |
| link | P53 E53 P74i | museum, where is it kept, who holds it, in the collection of, collection, curated by, which museum, where is it now, held in, owns repository, own repository, repository owned by, who owns repository, archive deposited with, where is the archive held, stored at, museum holding archive, deposited at, archive depository | accepted |
| date | E22 P140i E13 P141 | calibrated date, lab date | accepted |
| date | E22 P140i E13 P4 | when was it sampled, when was it tested | accepted |
| link | E53 P89i | related application areas, adjacent application areas, other application areas, neighbouring sites, associated application areas, overlapping application areas, linked application areas | accepted |
| link | E53 P17i | planning consultations, consultation, applications, which consultations | accepted |
| link | E53 P53i | affected monuments, archaeological sites, historic sites, heritage assets affected | accepted |
| link | E24 P140i E13 P140 | related wrecks, associated artefacts, linked heritage assets, related vessels, linked monuments, related artefacts, associated areas, related aircraft, linked records | accepted |
| link | E24 P67i E73 | bibliography, published in, literature, publications, books, reading list, source, further reading | accepted |
| date | O18i E11 P17 | launched, when was it launched, completed, laid down, shipbuilding date | accepted |
| link | O18i E11 P14 | shipbuilder, shipyard, who built it, shipwright, yard, building yard, builds, build, who builds | accepted |
| property | P41i E17 P137 | rigging, rig, rigged, sail plan, type of rigging, rigged as, how was it rigged | accepted |
| field | E11 P41i E17 P67i E73 P3 | construction history, build history, construction details | bench: adds no right answer |
| link | P17 E74 P107 | crew, crew member, crew members, sailors, who sailed on it, served on, seamen, on board, mariners, crewed by | accepted |
| property | P107 E21 P2 | crew role, rank, position on board, crew position, job on board, role on board, position in crew | accepted |
| field | E24 P129i E33 P3 | description, describe, summary, history, overview, tell me about, details, what is it, account, information, background, story | bench: worse on 4, e.g. catalina: what is the what is it of Brynquorn? |
| field | E24 P129i | pics, show me | bench: adds no right answer |
| date | P11i E7 P4 | owned from, period of ownership, ownership dates, bought, purchased, acquired, sold, changed hands, when was it owned | accepted |
| link | E24 P51 | who owned it, shipowner, proprietor, owners, owning company, belonged to, owns, own, who owns | accepted |
| date | P12i E13 P141 | scientifically dated, scientific date, radiocarbon date, dendro date, dendrochronological date, carbon dated, c14 date, scientific dating result, scientific dating, absolute date, dated scientifically | accepted |
| date | P12i E13 P4 | date determined, when was it dated, when was the sample dated, date of analysis, when was the date determined, when was it analysed, analysis date | accepted |
| property | P12i E13 P32 | dating method, how was it dated, dendrochronology, radiocarbon, method of dating, scientific dating method | bench: worse on 1, e.g. her: what is the how was it dated of Mavquorn? |
| date | P132 E5 P4 | in service, service life, in commission, active service, when was it in service, working life, decommissioned | accepted |
| link | P132 E5 P10 | used in which period, period of service | accepted |
| date | P16i E9 P17 | sank, sunk, wrecked, lost, went down, date of loss, when did it sink, when was it lost, when was it wrecked, shipwrecked, year of loss, date wrecked, date of sinking | accepted |
| date | P16i E9 P4 | sailed, set sail, voyage date, when did it sail, voyage, left port, date of departure, put to sea | accepted |
| date | E9 P4 E52 P82b | arrived, arrival date, date of arrival, reached port, docked, when did it arrive, came into port | accepted |
| date | P4 E52 P3 | expected arrival, due to arrive, expected date of arrival, eta | accepted |
| property | P25 E19 P2 | cargo, carrying, what was it carrying, freight, load, goods carried, cargo type, laden with | accepted |
| property | P27 E53 P1 E41 P3 | departed from, sailed from, port of departure, origin port, leaving from, where did it sail from, from which port | accepted |
| property | P17 E53 P1 E41 P3 | bound for, destination, heading to, sailing to, en route to, where was it going, port of destination, going to | accepted |
| field | E9 P129i E33 P3 | voyage description, account of voyage, voyage details, story of the voyage, last voyage | accepted |
| property | P67i E29 P2 | action, action type, required action, mitigation, what work is required, archaeological requirement, type of action, what archaeology is required, work required | accepted |
| field | P67i E29 P3 | action notes, action details, action text, description of action | accepted |
| date | P94i E65 P4 | advice given, advised, advice date, date of advice, when was advice given, advice issued, advice provided | accepted |
| field | P129i E29 P3 | advice, advice text, what was the advice, advice details, content of advice, our advice | accepted |
| link | P94i E65 P14 | advice given by, who advised, advisor, adviser, advised by, who gave the advice, who gave advice | accepted |
| link | E7 P17i | related activities, archaeological work carried out, surveys carried out | accepted |
| link | E7 P118 | related consultations, previous consultations, linked cases, other applications, related cases, associated consultations, earlier applications, previous applications | accepted |
| property | P17i E7 P9 E7 P2 | attendee type, attendee role, who were they, capacity of attendee | bench: worse on 3, e.g. catalina: what is the who were they of Kelquorn? |
| field | P9 E7 P129i E33 P3 | communication notes, what was discussed, notes of communication, conversation notes, call notes, meeting notes | bench: adds no right answer |
| field | P9 E7 P17 E33 P3 | follow on actions, follow up, follow-up, next steps, follow up actions, actions arising | accepted |
| link | P9 E7 P67i | communication file, email attachment, communication attachment, correspondence file | accepted |
| link | P9 E7 P11 | participants, who was contacted, communication participants, spoke to, who was spoken to, who was in the conversation, contacted person | accepted |
| link | Q11i SP6 P122 | application area, application site, red line boundary, site boundary, development site, application boundary, site area | accepted |
| field | SP6 P67i E33 P3 | site location, location description, whereabouts, situated, where is the site | bench: worse on 2, e.g. catalina: what is the location description of Kelquorn? |
| field | P17 E53 Q11i SP6 P168 | mapped location | bench: adds no right answer |
| date | E7 P4 E52 P86i | target date, deadline, due, due date, response due, by when, target response date, when is it due, deadline for response | bench: worse on 2, e.g. catalina: when was Kelquorn by when? |
| field | E7 P1 E41 P3 | name, title, consultation name, called, what is it called, consultation title, case name, known as, activity name, project name, event name, name of the investigation | bench: worse on 9, e.g. catalina: what is the called of Keldrith? |
| field | P11 E74 P2 | consulting contact, contact, point of contact, contact details | accepted |
| field | E7 P140i E13 P141 | contested heritage, contested, controversial, disputed heritage, is it contested | accepted |
| link | P129i E33 P165i | letter, response letter, advice letter, letter file, consultation letter, letter sent out | accepted |
| field | P17i E7 P129i | site photos, site photographs | bench: adds no right answer |
| link | P17 E33 P67i | proposal documents, proposal files, plans, drawings, submitted plans, application documents | accepted |
| link | P140i E15 P14 | agency, external agency, reference agency, issuing agency | accepted |
| date | P17i E7 P4 | site visit, visited, visit date, date of visit, went on site, when was the site visited, site inspection, site meeting | accepted |
| field | P17i E7 P4 E52 P3 | visit display date, approximate visit date, visit date as written | bench: adds no right answer |
| link | P141i E13 P140 | sites, related monuments, heritage assets, what monuments, buildings, artefacts, associated monuments, associated sites, listed buildings within, what is in it, features within, wrecks, what sites | accepted |
| date | P7i E5 P4 | date, when, phase date, date range, originated, origin, developed, came into being, age, when did it develop, when was it laid out, dating, when was it established | bench: worse on 4, e.g. catalina: when was Senquorn when? |
| property | E5 P41i E17 P141 | broad type, broad character, broad class, broad category, general category, broad classification, general type, broad character type, high level type | accepted |
| property | P141 E55 P127i | hlc type, character type, landscape type, land use type, what kind of landscape, historic land use, landscape character, townscape type, kind of area, what kind of area, character type classification, land use | accepted |
| link | P7i E5 P10 | of what period | accepted |
| property | P41i E17 P2 | confidence in classification | accepted |
| link | P41i E17 P16 | historic map, historic maps, old map, map source, which map, based on map, map evidence, ordnance survey map, tithe map, early map, first edition os, cartographic source, source map | accepted |
| field | E27 P1 E41 P3 | area name, name of site | bench: adds no right answer |
| link | E27 P12i | fieldwork, excavations, archaeological work, work carried out, what investigations, was it excavated, evaluation | accepted |
| link | E27 P16i | consultations, planning applications, planning cases, casework, planning consultation, development proposals | accepted |
| link | E27 P140i E13 P140 | finds from, buildings within, monuments within | accepted |
| link | E27 P67i | books about, source citation | accepted |
| property | E27 O18i E11 P41i E17 P141 | interpretation confidence | accepted |
| field | E27 P129i E33 P3 | what is known | bench: adds no right answer |
| link | E27 P129i D1 | pdfs | accepted |
| link | E27 P59i | parent area, within area, larger area, parent site, wider area | accepted |
| property | E27 P140i E13 P32 | dating technique, dated using | accepted |
| link | D1 P104 E30 P75i | credit, who owns it, copyright belongs to | accepted |
| property | D1 P104 E30 P2 | can i use it, public domain, reuse, terms of use | accepted |
| field | D1 P104 E30 P67i E33 P3 | attribution | bench: adds no right answer |
| date | L11i D7 P4 | taken, date taken, when was it taken, creation date, when was it created, photographed, scanned, date of creation, when was the photo taken, drawn | bench: worse on 4, e.g. catalina: what is the creation date of Bryndrith? |
| link | L11i D7 P14 | creator, taken by, photographer, who took it, who created it, authored by, who wrote it, drawn by, photographed by, creates, create, who creates | accepted |
| field | D1 P129i E33 P3 | what does it show, what is in it | bench: worse on 2, e.g. catalina: what is the what is in it of Bryndrith? |
| field | E24 P53 E53 P1 E41 P3 | aircraft address | bench: adds no right answer |
| date | P132 E11 P4 | assembled, when was it made, build date, date of manufacture, when manufactured, rolled off the production line, made in | accepted |
| field | P7 E53 P1 | place of manufacture, where was it built, where was it made, factory, built where, manufactured where, which factory, production site | bench: adds no right answer |
| property | P132 E11 P126 | materials, construction material, built from, airframe material, fabric or metal | accepted |
| link | P132 E11 P117 | from which era | accepted |
| property | P17 E17 P125 | aircraft type, type of aircraft, what kind of aircraft, what type of plane, kind of plane, aircraft model, model, what aircraft, plane type, make and model | accepted |
| property | P17 E17 P137 | aircraft form, form, configuration, monoplane or biplane, airframe type, shape of aircraft, wing configuration | accepted |
| property | P17 E17 P42 | aircraft function, role of the aircraft, military role | accepted |
| property | P17 E17 P32 | what evidence | accepted |
| link | E24 P12i | recovery operation | accepted |
| property | P132 E7 P9 E7 P2 | their role, role in | accepted |
| link | P11 E74 P107 | who flew it, pilot, pilots, aircrew, who was on board, airmen, flown by, who was flying, navigator, gunner | accepted |
| link | E24 P67i D1 | associated files, digital objects, reports | accepted |
| date | P93i E81 P4 | flight, flew, took off, departed, departure date, date of flight, when did it fly, last flight, final flight, flight date, mission date, sortie date | accepted |
| date | E81 P4 E52 P82b | crashed, shot down, when did it crash, crash date, came down, ditched, loss date, date crashed | accepted |
| date | E81 P4 E52 P86i | expected to arrive, estimated arrival | accepted |
| property | P12 E19 P2 | payload, bomb load | accepted |
| link | P93i E81 P92 | crash site, where did it crash, wreck site, where it came down, crash location, site of crash, wreckage site, where is the wreck, crash place | accepted |
| property | P92 E18 P2 | crash site type, type of crash site, what kind of crash site, kind of site where it crashed | accepted |
| field | E81 P129i E33 P3 | flight description, flight details, mission details, account of the flight, story of the flight, what happened on the flight, loss account | accepted |
| property | P108 E78 P2 | archive type, type of archive, archive material, what archive, archive contents, what records were produced | accepted |
| property | P9i E7 P9 E7 P2 | role type, what role, in what capacity | accepted |
| link | E7 P17 | what site, which monument, heritage assets investigated, site investigated, what was investigated, finds, buildings recorded | accepted |
| property | E7 P140i E13 P141 | status, published status, backlog, skeleton record | accepted |
| link | E74 P11i | fieldwork carried out, what work did they do, excavations carried out, surveys | accepted |
| property | E74 P141i E13 P2 | association type, type of association | demo bank worse: refused-should-answer -> wrong: what is related to Navan Fort? | Show the association type of Monument 'Navan Fort, Navan'. | 1 |  |
| field | E74 P129i E33 P3 | what do they do, profile | bench: worse on 2, e.g. catalina: what is the what do they do of Kelzabel? |
| date | P95i E66 P4 | set up, when was it founded, incorporated, founding date, date founded, year established, started, in existence, active dates, operating dates | accepted |
| date | E66 P4 E52 P82b | dissolved, closed, wound up, ceased, disbanded, shut down, when did it close, defunct since, ceased trading | accepted |
| property | P95i E66 P92 | kind of organisation, what sort of organisation, sector, what type of organisation, kind of body | accepted |
| link | E74 P107i | subsidiary of, parent company, department of, branch of, umbrella organisation | accepted |
| date | P141 E4 P4 | name used, name in use from, when was the name used, name usage dates, alternative name dates | accepted |
| link | P140i E13 P14 | name used by, who uses this name, alternative name used by, name coined by | accepted |
| field | P161 SP6 P168 | region, geographic extent, area covered, where was it | bench: adds no right answer |
| link | E4 P10 | parent period, broader period, subdivision of, larger period, main period | accepted |
| date | E4 P4 E52 P81b | ended, end, end date, when did it end, finished, close of, came to an end, latest end, concluded | bench: worse on 1, e.g. catalina: what is the end date of Dorzabel? |
| field | E4 P129i E33 P3 | characteristics, what was it like, definition | bench: adds no right answer |
| property | E4 P129i E33 P72 | description language | accepted |

## Gate checks

- bench: 154 pass alone and together (run 1)
- demo bank: nothing worse with the 152 passing
- HER plans: 125/125 answers as reviewed

Bench counts: right / wrong reading / refused / right refusal / wrong.

| set | mode | before | after |
| --- | --- | --- | --- |
| lingo | ontology | 41 / 0 / 7 / 2 / 0 | 85 / 0 / 7 / 2 / 0 |
| catalina | ontology | 749 / 0 / 175 / 54 / 0 | 2614 / 0 / 786 / 115 / 0 |
| her | ontology | 594 / 0 / 92 / 48 / 0 | 2275 / 0 / 632 / 108 / 0 |
| her | ontology+base | 583 / 0 / 103 / 48 / 0 | 2198 / 0 / 709 / 108 / 0 |
