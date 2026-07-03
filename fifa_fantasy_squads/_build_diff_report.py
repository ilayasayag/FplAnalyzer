#!/usr/bin/env python3
"""Build _diff_report.{json,md}: full lists of every diff between the LIVE
wc_players DB and the FIFA fantasy squads, by category:
  - position_diffs : player exists in both, positions disagree (DB vs FIFA)
  - missing_in_fifa: player in our DB but NOT found in FIFA squad (by name)
  - missing_in_db  : player in FIFA squad but NOT found in our DB (by name)

The position_diffs + missing_in_fifa blocks carry original DB names. The
missing_in_db block carried FIFA *normalized* names (extracted from the live
comparison run in-browser); we re-attach each one's original FIFA name +
position + price by re-normalizing the local FIFA squad files with the same
normaliser the browser used (NFKD -> drop combining marks -> lowercase ->
strip apostrophes/dots, hyphen->space -> drop any remaining non [a-z0-9 ]).
"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# FIFA abbr -> our DB iso alias (the comparison emitted DB isos)
FIFA_TO_DB = {"BIH": "BOS", "IRN": "IRA", "JPN": "JAP", "MAR": "MOR",
              "KSA": "SAU", "ESP": "SPA", "SUI": "SWI"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("'", "").replace(".", "").replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------- raw blocks
POSITION_DIFFS = """\
ALG|Ibrahim Maza|DB:MID|FIFA:FWD
ALG|Adil Boulbina|DB:FWD|FIFA:MID
ALG|Riyad Mahrez|DB:FWD|FIFA:MID
ARG|Julián Alvarez|DB:MID|FIFA:FWD
ARG|Thiago Almada|DB:FWD|FIFA:MID
ARG|Giuliano Simeone|DB:FWD|FIFA:MID
ARG|Nico Paz|DB:FWD|FIFA:MID
AUS|Kai Trewin|DB:MID|FIFA:DEF
AUS|Nishan Velupillay|DB:MID|FIFA:FWD
AUS|Lucas Herrington|DB:MID|FIFA:DEF
BEL|Charles De Ketelaere|DB:FWD|FIFA:MID
BEL|Alexis Saelemaekers|DB:FWD|FIFA:MID
BEL|Diego Moreira|DB:FWD|FIFA:MID
BRA|Ederson|DB:GK|FIFA:MID
BRA|Danilo|DB:DEF|FIFA:MID
BRA|Gabriel Martinelli|DB:FWD|FIFA:MID
BRA|Neymar|DB:FWD|FIFA:MID
BRA|Raphinha|DB:FWD|FIFA:MID
BRA|Vinicius Júnior|DB:FWD|FIFA:MID
CAN|Niko Sigur|DB:DEF|FIFA:MID
CAN|Tajon Buchanan|DB:MID|FIFA:FWD
CAN|Liam Millar|DB:MID|FIFA:FWD
COD|Aaron Tshibola|DB:DEF|FIFA:MID
COD|Meschack Elia|DB:MID|FIFA:FWD
COD|Nathanaël Mbuku|DB:MID|FIFA:FWD
COD|Brian Cipenga|DB:MID|FIFA:FWD
COD|Théo Bongonda|DB:FWD|FIFA:MID
COL|Luis Díaz|DB:FWD|FIFA:MID
COL|Jaminton Campaz|DB:FWD|FIFA:MID
CPV|Gilson Benchimol|DB:FWD|FIFA:MID
CPV|Helio Varela|DB:FWD|FIFA:MID
CRO|Kristijan Jakic|DB:DEF|FIFA:MID
CUW|Livano Comenencia|DB:MID|FIFA:DEF
CUW|Leandro Bacuna|DB:MID|FIFA:DEF
CUW|Tyrese Noslin|DB:MID|FIFA:DEF
CUW|Ar'jany Martha|DB:MID|FIFA:DEF
CUW|Tahith Chong|DB:FWD|FIFA:MID
CZE|David Douděra|DB:DEF|FIFA:MID
CZE|Pavel Šulc|DB:FWD|FIFA:MID
CZE|Denis Višinský|DB:FWD|FIFA:MID
ECU|Gonzalo Plata|DB:MID|FIFA:FWD
ECU|Alan Minda|DB:MID|FIFA:FWD
ECU|Yaimar Medina|DB:MID|FIFA:DEF
ECU|Nilson Angulo|DB:FWD|FIFA:MID
ECU|Anthony Valencia|DB:FWD|FIFA:MID
EGY|Mohamed Salah|DB:FWD|FIFA:MID
ENG|Marcus Rashford|DB:FWD|FIFA:MID
FRA|Maghnes Akliouche|DB:FWD|FIFA:MID
FRA|Ousmane Dembele|DB:FWD|FIFA:MID
GHA|Antoine Semenyo|DB:MID|FIFA:FWD
GHA|Ernest Nuamah|DB:FWD|FIFA:MID
IRA|Alireza Jahanbakhsh|DB:MID|FIFA:FWD
IRA|Saman Ghoddos|DB:MID|FIFA:FWD
IRQ|Youssef Amyn|DB:MID|FIFA:FWD
JAP|Ritsu Doan|DB:MID|FIFA:DEF
JAP|Daizen Maeda|DB:FWD|FIFA:MID
JOR|Amer Jamous|DB:MID|FIFA:DEF
JOR|Mahmoud Al-Mardi|DB:MID|FIFA:FWD
KOR|Park Jin-seob|DB:DEF|FIFA:MID
KOR|Jens Castrop|DB:DEF|FIFA:MID
KOR|Lee Gi-hyuk|DB:MID|FIFA:DEF
KOR|Hwang Hee-chan|DB:MID|FIFA:FWD
KOR|Yang Hyun-jun|DB:MID|FIFA:FWD
KOR|Eom Ji-sung|DB:MID|FIFA:FWD
MEX|Edson Álvarez|DB:DEF|FIFA:MID
MEX|César Huerta|DB:FWD|FIFA:MID
MOR|Brahim Diaz|DB:FWD|FIFA:MID
NED|Justin Kluivert|DB:FWD|FIFA:MID
NED|Crysencio Summerville|DB:FWD|FIFA:MID
NOR|Antonio Nusa|DB:FWD|FIFA:MID
NOR|Oscar Bobb|DB:FWD|FIFA:MID
NOR|Jens Petter Hauge|DB:FWD|FIFA:MID
NZL|Callum McCowatt|DB:FWD|FIFA:MID
NZL|Lachlan Bayliss|DB:FWD|FIFA:MID
PAN|Tomás Rodríguez|DB:MID|FIFA:FWD
PAR|Alexandro Maidana|DB:DEF|FIFA:FWD
PAR|Ramón Sosa|DB:MID|FIFA:FWD
PAR|Julio Enciso|DB:FWD|FIFA:MID
POR|Pedro Neto|DB:FWD|FIFA:MID
POR|Francisco Conceição|DB:FWD|FIFA:MID
QAT|Ayoub Al-Oui|DB:DEF|FIFA:MID
RSA|Tshepang Moremi|DB:FWD|FIFA:MID
RSA|Iqraam Rayners|DB:FWD|FIFA:MID
RSA|Kamogelo Sebelebele|DB:FWD|FIFA:MID
SAU|Mohammed Abu Al Shamat|DB:DEF|FIFA:MID
SCO|Findlay Curtis|DB:MID|FIFA:FWD
SEN|Krépin Diatta|DB:DEF|FIFA:MID
SEN|Sadio Mané|DB:FWD|FIFA:MID
SPA|Nico Williams|DB:FWD|FIFA:MID
SWE|Eric Smith|DB:DEF|FIFA:MID
SWE|Elliot Stroud|DB:DEF|FIFA:MID
SWE|Herman Johansson|DB:DEF|FIFA:MID
SWI|Rubén Vargas|DB:FWD|FIFA:MID
TUN|Elias Achouri|DB:FWD|FIFA:MID
TUR|Kaan Ayhan|DB:MID|FIFA:DEF
TUR|Arda Guler|DB:FWD|FIFA:MID
TUR|Can Uzun|DB:FWD|FIFA:MID
TUR|Irfan Can Kahveci|DB:FWD|FIFA:MID
TUR|Kenan Yildiz|DB:FWD|FIFA:MID
USA|Max Arfsten|DB:DEF|FIFA:FWD
USA|Brenden Aaronson|DB:FWD|FIFA:MID
USA|Christian Pulisic|DB:FWD|FIFA:MID
UZB|Abdulla Abdullaev|DB:DEF|FIFA:MID"""

MISSING_IN_FIFA = """\
ALG|Mohamed Amine Tougai
ALG|Mohamed Amoura
ALG|Nadhir Benbouali
ARG|Nicolás González
AUS|Maty Ryan
AUS|Paul Okon-Engstler
BRA|Alisson
COL|Juan Camilo Portilla
COL|Carlos Andrés Gómez
COL|Juan Camilo Hernández
CPV|Carlos Dos Santos
CPV|Marcio Rosa
CPV|Sidny Lopes Cabral
CPV|Roberto Lopes
CPV|Stopira (Ianique Tavares)
CPV|Diney Borges
CPV|Joao Paulo Fernandes
EGY|Rami Rabia
EGY|Hamdy Fathy
EGY|Mahmoud Trezeguet
EGY|Mostafa Abdelraouf Ziko
EGY|Haitham Hassan
EGY|Mohannad Lasheen
EGY|Nabil Emad Donga
EGY|Ahmed Sayed Zizo
EGY|Hamza Abdel Karim
GER|Pascal Groß
GHA|Abdul Rahman Baba
GHA|Prince Kwabena Adu
HAI|Josuée Duverger
HAI|Derrick Etienne Jr.
HAI|Josuée Casimir
IRA|Ehsan Hajsafi
IRA|Danial Iri
IRA|Shojae Khalilzadeh
IRA|Mohammad Hossein Kanaanizadegan
IRA|Arya Yousefi
IRA|Rouzbeh Cheshmi
IRA|Amirmohammad Razaghnian
IRA|Shahriar Moghanlou
IRA|Denis Dargahi
IRQ|Manaf Younis
IRQ|Zaid Ismail
IRQ|Ali Jassim
IRQ|Ali Yousef
JOR|Noor Bani Attiah
JOR|Abdullah Al-Fakhouri
JOR|Abdullah Nasib
JOR|Husam Abu Dahab
JOR|Mohammad Abualnadi
JOR|Anas Banawi
JOR|Ibrahim Saadeh
JOR|Mohammad Al-Dawoud
JOR|Odeh Al-Fakhouri
JOR|Mohammad Abu Zrayq
JOR|Ali Al-Azaizeh
MOR|Ahmed Reda Tagnaouti
MOR|Ayoube Amaimouni
MOR|Yassine Gessime
NOR|Orjan Haskjold Nyland
NOR|Marcus Holmgren Pedersen
NOR|David Moller Wolfe
NOR|Fredrik Bjorkan
NOR|Torbjorn Heggem
NOR|Leo Skiri Ostigard
NOR|Martin Odegaard
NOR|Alexander Sorloth
NOR|Jorgen Strand Larsen
NZL|Matt Garbett
NZL|Eli Just
PAN|Michael Amir Murillo
PAR|Juan Cáceres
PAR|Alejandro Romero Gamarra (Kaku)
PAR|Maurício
POR|Francisco Trincão
QAT|Mahmoud Abunada
QAT|Sultan Al-Braik
QAT|Homam Ahmed
QAT|Al-Hashmi Al-Hussain
QAT|Ahmed Fathi
QAT|Mohamed Al-Mannai
QAT|Ahmed Alaaeldin
RSA|Sphephelo Sithole
SAU|Hassan Tambakti
SAU|Hassan Kadesh
SAU|Nawaf Boushal
SAU|Mohammed Kanno
SAU|Alaa Al Hajji
SAU|Ayman Yahya
SAU|Feras Al Buraikan
SAU|Abdullah Al Hamdan
SEN|Idrissa Gana Gueye
TUN|Mouhib Chamakh
TUN|Mohamed Amine Ben Hamida
URU|Maximiliano Araújo
USA|Alex Freeman
USA|Gio Reyna
USA|Tim Weah
USA|Alejandro Zendejas
UZB|Abduvohid Nematov
UZB|Avazbek Ulmasaliev
UZB|Behruz Karimov
UZB|Azizjon Ganiev
UZB|Abbosbek Fayzullayev
UZB|Azizbek Amonov"""

MISSING_IN_DB = """\
ALG|abdelatif ramdane
ALG|anthony mandrea
ALG|kilian belazzoug
ALG|mohamed tougai
ALG|mehdi dorval
ALG|sohaib nair
ALG|adil aouchiche
ALG|mohammed amoura
ALG|ahmed benbouali
ALG|amin chiakha
ARG|walter benitez
ARG|facundo cambeses
ARG|santiago beltran
ARG|marcos senesi
ARG|marcos acuna
ARG|lucas martinez quarta
ARG|german pezzella
ARG|gabriel rojas
ARG|leonardo balerdi
ARG|kevin mac allister
ARG|agustin giay
ARG|zaid romero
ARG|lautaro di lollo
ARG|emiliano buendia
ARG|matias soule
ARG|franco mastantuono
ARG|gianluca prestianni
ARG|nico gonzalez
ARG|maximo perrone
ARG|guido rodriguez
ARG|alejandro garnacho
ARG|claudio echeverri
ARG|anibal moreno
ARG|equi fernandez
ARG|alan varela
ARG|nicolas dominguez
ARG|nicolas capaldo
ARG|tomas aranda
ARG|milton delgado
ARG|santiago castro
ARG|mateo pellegrino
AUS|mathew ryan
AUS|joe gauci
AUS|kye rowles
AUS|fran karacic
AUS|riley mcgree
AUS|alex robertson
AUS|patrick yazbek
AUS|paul okon
AUS|martin boyle
AUS|brandon borrello
AUS|deni juric
AUS|ante suto
BOS|osman hadzikic
BRA|alisson becker
CAN|zorhan bassong
CAN|jamie knight lebel
CAN|jayden nelson
CAN|ralph priso
CAN|jacen russell rowe
CAN|daniel jebbison
CIV|clement akpa
COD|simon banza
COL|juan portilla
COL|cucho hernandez
COL|andres gomez
CPV|cj dos santos
CPV|marcio da rosa
CPV|pico
CPV|sidny cabral
CPV|diney
CPV|stopira
CPV|joao paulo
CZE|pavel bucha
CZE|christophe kabongo
CZE|tomas ladra
ECU|cristhian loor
ECU|deinner ordonez
ECU|fricio caicedo
ECU|jose hurtado
ECU|bruno caicedo
ECU|luis fragozo
ECU|darwin guagua
ECU|ederson castillo
ECU|malcom dacosta
ECU|john mercado
EGY|mohamed alaa
EGY|ramy rabia
EGY|mohanad lasheen
EGY|hamdi fathy
EGY|zizo
EGY|nabil emad dunga
EGY|mostafa zico
EGY|trezeguet
EGY|haissem hassan
EGY|aqtay abdallah
EGY|hamza abdelkarim
GER|jonas urbig
GER|pascal gro
GER|lennart karl
GHA|paul reverson
GHA|solomon agbasi
GHA|alexander djiku
GHA|abdul baba
GHA|prince adu
HAI|josue duverger
HAI|derrick etienne
HAI|josue casimir
IRA|mohammad khalifeh
IRA|hossein kanani
IRA|shoja khalilzadeh
IRA|ehsan hajisafi
IRA|aria yousefi
IRA|danial eiri
IRA|omid noorafkan
IRA|roozbeh cheshmi
IRA|hadi habibinejad
IRA|amir mohammad razzaghinia
IRA|kasra taheri
IRA|shahriyar moghanlou
IRA|dennis dargahi
IRA|amirhossein mahmoudi
IRQ|kumel saadi
IRQ|maytham jabbar
IRQ|munaf younus
IRQ|ahmed maknzi
IRQ|dario naamo
IRQ|peter gwargis
IRQ|hasan abdulkareem
IRQ|zaid ismael
IRQ|jussef nasrawe
IRQ|karar nabeel
IRQ|ali jasim
IRQ|ali yousif
JAP|maya yoshida
JOR|abdallah al fakhouri
JOR|nour bani ateyah
JOR|ahmad al juaidi
JOR|abdallah nasib
JOR|husam abu al dahab
JOR|mohammad abu ghoush
JOR|ahmad assaf
JOR|mohammad abu al nadi
JOR|anas badawi
JOR|mohammad al daoud
JOR|ibrahim sadeh
JOR|yousef qashi
JOR|mohammad abu zraiq
JOR|ali azaizeh
JOR|odeh fakhoury
KOR|cho yu min
MEX|antonio rodriguez
MEX|carlos moreno
MEX|alex padilla
MEX|julian araujo
MEX|jesus angulo
MEX|richard ledezma
MEX|ramon juarez
MEX|victor guzman
MEX|everardo lopez
MEX|alejandro gomez
MEX|bryan gonzalez
MEX|carlos rodriguez
MEX|marcel ruiz
MEX|diego lainez
MEX|efrain alvarez
MEX|jordan carrillo
MEX|kevin castaneda
MEX|alexis gutierrez
MEX|jeremy marquez
MEX|erick sanchez
MEX|elias montiel
MEX|german berterame
MEX|jorge ruvalcaba
MEX|alexei dominguez
MOR|el mehdi al harrar
MOR|ibrahim gomis
MOR|yanis benchaouch
MOR|ahmed tagnaouti
MOR|souffian el karouani
MOR|soufiane bouftini
MOR|mohamed chibi
MOR|ismael baouf
MOR|abdelhamid ait boudlal
MOR|sofiane boufal
MOR|imran louza
MOR|oussama targhalline
MOR|yanis begraoui
MOR|soufiane el faouzi
MOR|marwane saadane
MOR|othmane maamma
MOR|amine sbai
MOR|soufiane benjdida
MOR|tawfik bentayeb
MOR|ayoube amaimouni echghouyab
MOR|gessime yassine
MOR|rayane bounida
MOR|yassir zabiri
NED|justin bijlow
NED|jeremie frimpong
NED|lutsharel geertruida
NED|stefan de vrij
NED|xavi simons
NED|jerdy schouten
NED|luciano valente
NED|kees smit
NOR|rjan nyland
NOR|marcus pedersen
NOR|leo stigard
NOR|david mller wolfe
NOR|fredrik bjrkan
NOR|torbjrn heggem
NOR|martin degaard
NOR|alexander srloth
NOR|jrgen strand larsen
NZL|elijah just
NZL|matthew garbett
PAN|jd gunn
PAN|amir murillo
PAN|jose murillo
PAN|ivan anderson
PAN|martin krug
PAN|victor griffith
PAN|kadir barria
PAR|carlos coronel
PAR|juan espinola
PAR|santiago rojas
PAR|blas riveros
PAR|mateo gamarra
PAR|alan benitez
PAR|juan jose caceres
PAR|ronaldo dejesus
PAR|agustin sandez
PAR|saul salcedo
PAR|alcides benitez
PAR|alan nunez
PAR|diego leon
PAR|lucas romero
PAR|lorenzo melgarejo
PAR|enso gonzalez
PAR|diego gonzalez
PAR|ruben lezcano
PAR|ronaldo martinez
PAR|angel romero
PAR|hugo cuenca
PAR|rodney redes
PAR|alejandro romero
PAR|robert piris da motta
PAR|mauricio magalhaes prado
PAR|oscar romero
PAR|mathias villasanti
PAR|alvaro campuzano
PAR|carlos gonzalez
PAR|adam bareiro
PAR|robert morales
PAR|adrian alcaraz
POR|ricardo velho
POR|trincao
QAT|fahad younis
QAT|shehab ellethy
QAT|mahmud abunada
QAT|bassam al rawi
QAT|tarek salman
QAT|sultan al brake
QAT|homam el amin
QAT|niall mason
QAT|hashmi al hussain
QAT|rayyan al ali
QAT|mohammed waad
QAT|ahmed fathy
QAT|mohammad al mannai
QAT|ahmed alaa
QAT|sebastian soria
QAT|mubarak shanan
RSA|brandon petersen
RSA|thapelo morena
RSA|thabiso monyane
RSA|patrick maswanganyi
RSA|yaya sithole
RSA|lebohang maboe
RSA|brooklyn poggenpoel
SAU|abdulquddus atiah
SAU|abdulrahman al sanbi
SAU|hassan al tambakti
SAU|zakaria hawsawi
SAU|hassan kadish
SAU|nawaf bu washl
SAU|aiman yahya
SAU|mohamed kanno
SAU|alaa al hejji
SAU|feras al brikan
SAU|saleh abu al shamat
SAU|abdullah al salem
SAU|abdullah al hamddan
SCO|billy gilmour
SEN|pape sy
SEN|ilay camara
SEN|moustapha mbow
SEN|idrissa gueye
SWE|emil holm
SWE|sebastian nanasi
TUN|abdelmouhib chamakh
TUN|mohamed amine ben hmida
TUR|ersin destanoglu
TUR|muhammed sengezer
TUR|yusuf akcicek
TUR|mustafa eskihellac
TUR|ahmetcan kaplan
TUR|yusuf sari
TUR|atakan karazor
TUR|aral simsir
TUR|demir ege tiknaz
URU|jose rodriguez
URU|brian barboza
URU|benjamin garcia
URU|maxi araujo
URU|nicolas fonseca
URU|luciano gonzalez
URU|pablo alcoba
URU|facundo torres
URU|facundo martinez
URU|agustin alvarez
USA|patrick schulte
USA|alexander freeman
USA|johnny cardoso
USA|timothy weah
USA|tanner tessmann
USA|aidan morris
USA|giovanni reyna
USA|alex zendejas
USA|patrick agyemang
UZB|abduvokhid nematov
UZB|avazbek olmasaliev
UZB|bekhruz karimov
UZB|abbosbek fayzullaev
UZB|aziz ganiev
UZB|umarali rakhmonaliev
UZB|jasurbek jaloliddinov
UZB|ruslanbek jiyanov
UZB|sherzod temirov
UZB|azizbek amanov"""


def main():
    # Build a {db_iso: {norm: fifa_player}} index from the local FIFA files
    idx = {}
    for fn in os.listdir(HERE):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        with open(os.path.join(HERE, fn), encoding="utf-8") as f:
            data = json.load(f)
        db_iso = FIFA_TO_DB.get(data.get("abbr"), data.get("abbr"))
        bucket = idx.setdefault(db_iso, {})
        for p in data.get("players", []):
            bucket[norm(p["name"])] = p

    # position_diffs
    pos_diffs = []
    for line in POSITION_DIFFS.splitlines():
        iso, name, dbp, fifap = line.split("|")
        pos_diffs.append({
            "team": iso,
            "player": name,
            "db_position": dbp.split(":")[1],
            "fifa_position": fifap.split(":")[1],
        })

    # missing_in_fifa (our DB has them, FIFA doesn't)
    miss_fifa = []
    for line in MISSING_IN_FIFA.splitlines():
        iso, name = line.split("|")
        miss_fifa.append({"team": iso, "player": name})

    # missing_in_db (FIFA has them, our DB doesn't) -- enrich w/ original name+pos
    miss_db = []
    unmatched = []
    for line in MISSING_IN_DB.splitlines():
        iso, nn = line.split("|")
        p = idx.get(iso, {}).get(nn)
        if p:
            miss_db.append({
                "team": iso,
                "player": p["name"],
                "fifa_position": p.get("position"),
                "fifa_price": p.get("price"),
                "fifa_total_points": p.get("totalPoints"),
            })
        else:
            miss_db.append({"team": iso, "player": nn, "fifa_position": None,
                            "_normalized_only": True})
            unmatched.append(f"{iso}|{nn}")

    report = {
        "comparison": "LIVE wc_players DB  vs  FIFA fantasy squads (play.fifa.com)",
        "match_method": "exact normalized full-name match within each national team",
        "totals": {
            "position_diffs": len(pos_diffs),
            "missing_in_fifa": len(miss_fifa),
            "missing_in_db": len(miss_db),
        },
        "legend": {
            "position_diffs": "player in BOTH, position disagrees (db_position vs fifa_position)",
            "missing_in_fifa": "in our DB, NOT found in the FIFA squad",
            "missing_in_db": "in the FIFA squad, NOT found in our DB",
        },
        "position_diffs": sorted(pos_diffs, key=lambda x: (x["team"], x["player"])),
        "missing_in_fifa": sorted(miss_fifa, key=lambda x: (x["team"], x["player"])),
        "missing_in_db": sorted(miss_db, key=lambda x: (x["team"], x["player"])),
    }

    out_json = os.path.join(HERE, "_diff_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # human-readable markdown grouped by team
    teams = sorted(set([d["team"] for d in pos_diffs]
                       + [d["team"] for d in miss_fifa]
                       + [d["team"] for d in miss_db]))
    lines = []
    lines.append("# FIFA squads vs live DB — full diff report\n")
    lines.append(f"- Position differences: **{len(pos_diffs)}**")
    lines.append(f"- In DB but missing in FIFA: **{len(miss_fifa)}**")
    lines.append(f"- In FIFA but missing in DB: **{len(miss_db)}**\n")
    for t in teams:
        pd = [d for d in pos_diffs if d["team"] == t]
        mf = [d for d in miss_fifa if d["team"] == t]
        md = [d for d in miss_db if d["team"] == t]
        if not (pd or mf or md):
            continue
        lines.append(f"\n## {t}")
        if pd:
            lines.append("\n**Position differs (DB → FIFA):**")
            for d in pd:
                lines.append(f"- {d['player']}: {d['db_position']} → {d['fifa_position']}")
        if mf:
            lines.append("\n**In our DB, missing in FIFA:**")
            for d in mf:
                lines.append(f"- {d['player']}")
        if md:
            lines.append("\n**In FIFA, missing in our DB:**")
            for d in md:
                pos = d.get("fifa_position") or "?"
                lines.append(f"- {d['player']} ({pos})")
    out_md = os.path.join(HERE, "_diff_report.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"position_diffs   : {len(pos_diffs)}")
    print(f"missing_in_fifa  : {len(miss_fifa)}")
    print(f"missing_in_db    : {len(miss_db)}")
    print(f"  of which enriched w/ original FIFA name+pos: {len(miss_db) - len(unmatched)}")
    print(f"  unmatched (kept normalized): {len(unmatched)}")
    if unmatched:
        print("  -> " + ", ".join(unmatched))
    print(f"\nWrote {out_json}")
    print(f"Wrote {out_md}")


if __name__ == "__main__":
    main()
