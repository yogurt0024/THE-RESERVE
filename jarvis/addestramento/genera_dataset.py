"""Crea dataset.jsonl, gli esempi con cui si addestra il modello "jarvis".

Ogni esempio è una conversazione completa nello stesso formato che Jarvis manda a Ollama:
il prompt di sistema vero (cervello.prompt_di_sistema), gli strumenti veri (strumenti.schemi),
le chiamate agli strumenti con i risultati prodotti dalle funzioni di strumenti.py
(con dati finti al posto di internet) e le risposte nello stile di Jarvis.

Uso: python genera_dataset.py
"""

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA.parent))

import cervello  # noqa: E402
import strumenti  # noqa: E402
from dialoghi import CONVERSAZIONI, CONVERSAZIONI_LUNGHE  # noqa: E402

MODELLO = "jarvis"
FILE_DATASET = CARTELLA / "dataset.jsonl"
caso = random.Random(2026)  # stesso codice, stesso dataset

APPELLATIVI = ["signore"] * 7 + ["signora", "capo", ""]
CITTA_UTENTE = ["Cagliari", "Sassari", "Olbia", "Nuoro", "Torino", "Milano", "Roma", "Bologna"]

# (in prima persona, come lo scrive l'utente; in seconda persona, come lo dice Jarvis)
FATTI = [
    ("Il mio gioco preferito è Minecraft", "il suo gioco preferito è Minecraft"),
    ("Gioco a Minecraft con un amico che vive in Piemonte", "gioca a Minecraft con un amico che vive in Piemonte"),
    ("Venerdì ho la verifica di matematica", "venerdì ha la verifica di matematica"),
    ("Il mio colore preferito è il blu", "il suo colore preferito è il blu"),
    ("Mi piace la pizza margherita", "le piace la pizza margherita"),
    ("Il mio cane si chiama Briciola", "il suo cane si chiama Briciola"),
    ("Tifo per il Cagliari", "tifa per il Cagliari"),
    ("Studio al liceo scientifico", "studia al liceo scientifico"),
    ("Mi alzo alle 7 per andare a scuola", "si alza alle 7 per andare a scuola"),
]
SECONDA_PERSONA = dict(FATTI)


class Contesto:
    """Una situazione a caso: data e ora, come chiamare l'utente, città, cose in memoria."""

    def __init__(self, fatti=None):
        self.adesso = datetime(2026, 1, 1) + timedelta(minutes=caso.randrange(365 * 24 * 60))
        self.titolo = caso.choice(APPELLATIVI)
        self.citta = caso.choice(CITTA_UTENTE) if caso.random() < 0.6 else ""
        self.fatti = fatti if fatti is not None else [f for f, _ in caso.sample(FATTI, caso.choice([0, 0, 1, 2, 3]))]
        self.config = dict(cervello.CONFIG_PREDEFINITA, come_chiamarmi=self.titolo, citta=self.citta)

    def t(self, testo):
        return testo.replace("{T}", f", {self.titolo}" if self.titolo else "")


def utente(testo):
    return {"role": "user", "content": testo}


def chiama(*chiamate):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"type": "function", "function": {"name": n, "arguments": a}} for n, a in chiamate]}


def risultato(testo):
    return {"role": "tool", "content": testo}


def esempio(ctx, messaggi, con_strumenti=True):
    for m in messaggi:
        if m["role"] == "assistant":
            m["content"] = ctx.t(m["content"])
    # Jarvis userà il modello addestrato in modalità ibrida, con Claude a disposizione.
    sistema = cervello.prompt_di_sistema(ctx.config, MODELLO, {"completion", "tools"}, ctx.fatti, ctx.adesso,
                                         cervello_avanzato=True)
    return {"messages": [{"role": "system", "content": sistema}] + messaggi,
            "tools": strumenti.schemi(ctx.config) + [cervello.STRUMENTO_AVANZATO] if con_strumenti else None}


def jarvis(testo):
    return {"role": "assistant", "content": testo}


def ore(ctx, minuti=0):
    return f"{ctx.adesso + timedelta(minutes=minuti):%H:%M}"


# --- Meteo -------------------------------------------------------------------------------

CITTA = {
    "Cagliari": ("Sardegna", "Italia", "mite"), "Sassari": ("Sardegna", "Italia", "mite"),
    "Olbia": ("Sardegna", "Italia", "mite"), "Nuoro": ("Sardegna", "Italia", "fresco"),
    "Oristano": ("Sardegna", "Italia", "mite"), "Torino": ("Piemonte", "Italia", "continentale"),
    "Milano": ("Lombardia", "Italia", "continentale"), "Roma": ("Lazio", "Italia", "mite"),
    "Napoli": ("Campania", "Italia", "mite"), "Firenze": ("Toscana", "Italia", "continentale"),
    "Bologna": ("Emilia-Romagna", "Italia", "continentale"), "Venezia": ("Veneto", "Italia", "continentale"),
    "Palermo": ("Sicilia", "Italia", "caldo"), "Bari": ("Puglia", "Italia", "mite"),
    "Genova": ("Liguria", "Italia", "mite"), "Trento": ("Trentino-Alto Adige", "Italia", "freddo"),
    "Londra": ("Inghilterra", "Regno Unito", "oceanico"), "Parigi": ("Île-de-France", "Francia", "oceanico"),
    "New York": ("New York", "Stati Uniti", "continentale"), "Tokyo": ("Tokyo", "Giappone", "mite"),
}
MEDIE = {  # temperatura media mese per mese
    "mite": [11, 11, 13, 15, 19, 23, 26, 27, 23, 20, 15, 12],
    "fresco": [7, 8, 10, 12, 16, 21, 24, 24, 20, 16, 11, 8],
    "caldo": [13, 13, 15, 17, 21, 25, 28, 28, 25, 22, 17, 14],
    "continentale": [2, 4, 9, 13, 18, 22, 25, 24, 20, 14, 8, 3],
    "freddo": [-1, 1, 6, 10, 15, 19, 21, 21, 16, 11, 5, 0],
    "oceanico": [6, 6, 9, 11, 14, 17, 19, 19, 16, 13, 9, 6],
}
FRASE_CIELO = {
    0: "cielo sereno", 1: "cielo quasi sereno", 2: "qualche nuvola", 3: "cielo coperto", 45: "nebbia",
    61: "pioggia debole", 63: "pioggia", 65: "pioggia forte", 71: "neve debole", 73: "neve",
    80: "qualche rovescio", 81: "rovesci", 95: "temporali",
}
PIOVOSI = {61, 63, 65, 80, 81, 95}


def _giorno_meteo(media):
    media += caso.uniform(-3, 3)
    minima, massima = media - caso.uniform(3, 6), media + caso.uniform(3, 6)
    if massima <= 3 and caso.random() < 0.5:
        codice = caso.choice([71, 73])
    else:
        codice = caso.choices([0, 1, 2, 3, 45, 61, 63, 65, 80, 81, 95],
                              [14, 10, 10, 8, 2, 5, 4, 1, 3, 2, 1])[0]
    if codice in PIOVOSI or codice in (71, 73):
        pioggia = caso.randrange(55, 96, 5)
    elif codice in (2, 3, 45):
        pioggia = caso.randrange(5, 40, 5)
    else:
        pioggia = caso.choice([0, 0, 5, 10])
    if caso.random() < 0.05:
        pioggia = None
    return {"codice": codice, "min": minima, "max": massima, "pioggia": pioggia}


def dati_meteo(ctx, citta):
    """Fa girare il vero strumenti.meteo con dati inventati. Restituisce (testo dello strumento, dati)."""
    regione, paese, clima = CITTA[citta]
    media = MEDIE[clima][ctx.adesso.month - 1]
    giorni = [_giorno_meteo(media) for _ in range(3)]
    oggi = giorni[0]
    quota = max(0.0, 1 - abs(ctx.adesso.hour + ctx.adesso.minute / 60 - 15) / 12)  # più caldo verso le 15
    adesso = {"temp": oggi["min"] + (oggi["max"] - oggi["min"]) * quota, "codice": oggi["codice"],
              "umidita": caso.randrange(35, 95), "vento": caso.uniform(2, 35)}
    adesso["percepita"] = adesso["temp"] - caso.uniform(0, 3)
    date_giorni = [(ctx.adesso.date() + timedelta(days=i)).isoformat() for i in range(3)]

    def scarica(url, parametri=None):
        if "geocoding" in url:
            return json.dumps({"results": [{"name": citta, "latitude": 0, "longitude": 0,
                                            "admin1": regione, "country": paese}]}).encode()
        return json.dumps({
            "current": {"temperature_2m": adesso["temp"], "apparent_temperature": adesso["percepita"],
                        "relative_humidity_2m": adesso["umidita"], "weather_code": adesso["codice"],
                        "wind_speed_10m": adesso["vento"]},
            "daily": {"time": date_giorni, "weather_code": [g["codice"] for g in giorni],
                      "temperature_2m_max": [g["max"] for g in giorni],
                      "temperature_2m_min": [g["min"] for g in giorni],
                      "precipitation_probability_max": [g["pioggia"] for g in giorni]},
        }).encode()

    strumenti._scarica = scarica
    return strumenti.meteo(citta), {"adesso": adesso, "giorni": giorni}


def g(valore):
    return f"{round(valore)}"


def consiglio(giorno):
    c = giorno["codice"]
    if c == 95:
        return "Se può, eviti di stare all'aperto durante i temporali."
    if c in PIOVOSI or (giorno["pioggia"] or 0) >= 60:
        return caso.choice(["Le consiglio l'ombrello.", "Un ombrello sarebbe una scelta saggia.",
                            "Meglio non uscire senza ombrello."])
    if c in (71, 73):
        return "Si copra bene e faccia attenzione alle strade."
    if c == 45:
        return "Con la nebbia, prudenza se si mette in strada."
    if giorno["max"] >= 32:
        return "Farà molto caldo: acqua a portata di mano e niente sole nelle ore centrali."
    if giorno["min"] <= 3:
        return "Fa freddo: le suggerisco un cappotto pesante."
    if c in (0, 1) and 18 <= giorno["max"] <= 28:
        return caso.choice(["Una giornata ideale per uscire.", "Nessun ostacolo meteorologico ai suoi piani."])
    return ""


def frase_pioggia(giorno):
    p = giorno["pioggia"]
    return "" if p is None else f", probabilità di pioggia {p}%"


def risposta_meteo(tipo, citta, dati):
    a, (oggi, domani, dopodomani) = dati["adesso"], dati["giorni"]
    if tipo == "adesso":
        testo = (f"A {citta} ci sono {g(a['temp'])} gradi e {FRASE_CIELO[a['codice']]}{{T}}. "
                 f"Per oggi la massima è di {g(oggi['max'])} gradi{frase_pioggia(oggi)}.")
        return f"{testo} {consiglio(oggi)}".strip()
    if tipo == "domani":
        testo = (f"Domani a {citta}: {FRASE_CIELO[domani['codice']]}, tra {g(domani['min'])} e "
                 f"{g(domani['max'])} gradi{frase_pioggia(domani)}{{T}}.")
        return f"{testo} {consiglio(domani)}".strip()
    if tipo == "pioggia":
        p = domani["pioggia"] or 0
        if domani["codice"] in PIOVOSI or p >= 50:
            return (f"Sì{{T}}: per domani a {citta} le previsioni danno {FRASE_CIELO[domani['codice']]}, con una "
                    f"probabilità di pioggia del {p}%. L'ombrello è d'obbligo.")
        return (f"Non sembra{{T}}: per domani a {citta} le previsioni danno {FRASE_CIELO[domani['codice']]}, con una "
                f"probabilità di pioggia del {p}%. L'ombrello può restare a casa.")
    if tipo == "temperatura":
        t = round(a["temp"])
        commento = ("Fa freddo: meglio coprirsi bene." if t <= 8 else
                    "Fa caldo: si ricordi di bere." if t >= 28 else "Una temperatura piacevole.")
        return f"A {citta} ci sono {t} gradi{{T}}, percepiti {g(a['percepita'])}. {commento}"
    if tipo == "dopodomani":
        return (f"Dopodomani a {citta}: {FRASE_CIELO[dopodomani['codice']]}, minima di {g(dopodomani['min'])} "
                f"e massima di {g(dopodomani['max'])} gradi{frase_pioggia(dopodomani)}{{T}}.")
    righe = [f"Ecco le previsioni per {citta}{{T}}:"]
    for nome, giorno in (("oggi", oggi), ("domani", domani), ("dopodomani", dopodomani)):
        righe.append(f"- {nome}: {FRASE_CIELO[giorno['codice']]}, tra {g(giorno['min'])} e {g(giorno['max'])} "
                     f"gradi{frase_pioggia(giorno)}")
    peggiore = max((oggi, domani, dopodomani), key=lambda x: (x["codice"] in PIOVOSI, x["pioggia"] or 0))
    return "\n".join(righe) + (f"\n{consiglio(peggiore)}" if consiglio(peggiore) else "")


DOMANDE_METEO = {
    "adesso": ["Che tempo fa a {c}?", "Com'è il meteo a {c}?", "Che tempo c'è a {c} adesso?", "Meteo {c}",
               "Com'è il tempo a {c}?"],
    "domani": ["Che tempo farà domani a {c}?", "Domani com'è il tempo a {c}?", "Previsioni per domani a {c}?"],
    "pioggia": ["Domani piove a {c}?", "Devo prendere l'ombrello domani a {c}?", "Pioverà domani a {c}?"],
    "temperatura": ["Quanti gradi ci sono a {c}?", "Che temperatura c'è a {c}?", "Fa freddo a {c}?"],
    "dopodomani": ["Che tempo farà dopodomani a {c}?", "E dopodomani a {c} che tempo fa?"],
    "tre_giorni": ["Previsioni dei prossimi giorni a {c}?", "Com'è il meteo a {c} nei prossimi giorni?"],
}
DOMANDE_METEO_MIA_CITTA = {"adesso": ["Che tempo fa?", "Com'è il tempo oggi?", "Com'è fuori?"],
                           "domani": ["Che tempo farà domani?", "Domani com'è il tempo?"],
                           "pioggia": ["Domani piove?", "Mi serve l'ombrello domani?"]}


def esempi_meteo():
    esempi = []
    for tipo, numero in (("adesso", 15), ("domani", 12), ("pioggia", 10), ("temperatura", 8),
                         ("dopodomani", 5), ("tre_giorni", 8)):
        for _ in range(numero):
            ctx, citta = Contesto(), caso.choice(list(CITTA))
            testo, dati = dati_meteo(ctx, citta)
            esempi.append(esempio(ctx, [utente(caso.choice(DOMANDE_METEO[tipo]).format(c=citta)),
                                        chiama(("meteo", {"citta": citta})), risultato(testo),
                                        jarvis(risposta_meteo(tipo, citta, dati))]))
    for _ in range(14):  # senza dire la città: si usa quella del prompt
        ctx = Contesto()
        ctx.citta = ctx.config["citta"] = caso.choice(CITTA_UTENTE)
        tipo = caso.choice(list(DOMANDE_METEO_MIA_CITTA))
        testo, dati = dati_meteo(ctx, ctx.citta)
        esempi.append(esempio(ctx, [utente(caso.choice(DOMANDE_METEO_MIA_CITTA[tipo])),
                                    chiama(("meteo", {"citta": ctx.citta})), risultato(testo),
                                    jarvis(risposta_meteo(tipo, ctx.citta, dati))]))
    for _ in range(3):  # senza città né nel messaggio né nel prompt: si chiede
        ctx = Contesto()
        ctx.citta = ctx.config["citta"] = ""
        esempi.append(esempio(ctx, [utente(caso.choice(["Che tempo fa?", "Domani piove?"])),
                                    jarvis("Di quale città{T}? Se me lo dice una volta, posso anche "
                                           "ricordarmelo per le prossime.")]))
    for citta in ("Atlantide", "Gotham", "Xyzk"):  # città che non esiste
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(f"Che tempo fa a {citta}?"), chiama(("meteo", {"citta": citta})),
                                    risultato(f'Errore: non trovo la città "{citta}".'),
                                    jarvis(f"Non trovo {citta} sulle mie mappe{{T}}. Forse è scritta in modo "
                                           "diverso, o è una città di fantasia? Mi dia un altro nome e riprovo.")]))
    for _ in range(3):  # senza internet
        ctx, citta = Contesto(), caso.choice(list(CITTA))
        esempi.append(esempio(ctx, [utente(f"Che tempo fa a {citta}?"), chiama(("meteo", {"citta": citta})),
                                    risultato("Errore: non riesco a collegarmi a internet."),
                                    jarvis("Non riesco a collegarmi a internet in questo momento{T}. Controlli la "
                                           "connessione e riproviamo.")]))
    return esempi


# --- Wikipedia ---------------------------------------------------------------------------

VOCI = [
    ("Grazia Deledda",
     "Grazia Deledda (Nuoro, 27 settembre 1871 – Roma, 15 agosto 1936) è stata una scrittrice italiana. Vinse il "
     "premio Nobel per la letteratura nel 1926, unica donna italiana ad averlo ricevuto. Tra le sue opere più "
     "note figurano Elias Portolu, Cenere, Canne al vento e La madre.",
     "Grazia Deledda era una scrittrice nata a Nuoro nel 1871 e morta a Roma nel 1936{T}. Nel 1926 vinse il "
     "Nobel per la letteratura: è tuttora l'unica donna italiana ad averlo ricevuto. Il suo romanzo più celebre "
     "è Canne al vento."),
    ("Antonio Gramsci",
     "Antonio Gramsci (Ales, 22 gennaio 1891 – Roma, 27 aprile 1937) è stato un politico, filosofo e giornalista "
     "italiano. Fu tra i fondatori del Partito Comunista d'Italia nel 1921. Arrestato dal regime fascista nel "
     "1926, durante la prigionia scrisse i Quaderni del carcere.",
     "Antonio Gramsci, nato ad Ales, in Sardegna, nel 1891, fu un politico, filosofo e giornalista{T}. Nel 1921 "
     "fu tra i fondatori del Partito Comunista d'Italia; arrestato dal regime fascista nel 1926, in prigione "
     "scrisse i Quaderni del carcere. Morì a Roma nel 1937."),
    ("Giuseppe Garibaldi",
     "Giuseppe Garibaldi (Nizza, 4 luglio 1807 – Caprera, 2 giugno 1882) è stato un generale, patriota e "
     "condottiero italiano. È noto soprattutto per la spedizione dei Mille del 1860, che portò alla conquista "
     "del Regno delle Due Sicilie e contribuì all'unità d'Italia. Trascorse gli ultimi anni sull'isola di "
     "Caprera, in Sardegna.",
     "Giuseppe Garibaldi fu un generale e patriota, nato a Nizza nel 1807{T}. È ricordato soprattutto per la "
     "spedizione dei Mille del 1860, decisiva per l'unità d'Italia. Passò gli ultimi anni a Caprera, in "
     "Sardegna, dove morì nel 1882."),
    ("Marie Curie",
     "Maria Salomea Skłodowska, nota come Marie Curie (Varsavia, 7 novembre 1867 – Passy, 4 luglio 1934), è "
     "stata una fisica e chimica polacca naturalizzata francese. Fu la prima donna a vincere un premio Nobel e "
     "l'unica persona ad averne vinti due in discipline scientifiche diverse: per la fisica nel 1903 e per la "
     "chimica nel 1911.",
     "Marie Curie era una fisica e chimica polacca, naturalizzata francese, vissuta dal 1867 al 1934{T}. Fu la "
     "prima donna a vincere un Nobel, ed è l'unica persona ad averne vinti due in scienze diverse: fisica nel "
     "1903 e chimica nel 1911."),
    ("Alan Turing",
     "Alan Mathison Turing (Londra, 23 giugno 1912 – Wilmslow, 7 giugno 1954) è stato un matematico, logico e "
     "crittografo britannico, considerato uno dei padri dell'informatica. Durante la seconda guerra mondiale "
     "contribuì a decifrare i messaggi della macchina Enigma. Propose il test di Turing per valutare "
     "l'intelligenza di una macchina.",
     "Alan Turing, matematico britannico vissuto dal 1912 al 1954, è considerato uno dei padri "
     "dell'informatica{T}. Durante la Seconda guerra mondiale contribuì a decifrare i messaggi della macchina "
     "Enigma, e propose il celebre test di Turing sull'intelligenza delle macchine. In un certo senso, un "
     "antenato professionale."),
    ("Minecraft",
     "Minecraft è un videogioco sandbox sviluppato da Mojang Studios. Creato da Markus Persson, è stato "
     "pubblicato ufficialmente nel novembre 2011. Nel 2014 Mojang è stata acquistata da Microsoft. È uno dei "
     "videogiochi più venduti della storia.",
     "Minecraft è un videogioco sandbox creato da Markus Persson e sviluppato da Mojang Studios{T}. È uscito "
     "ufficialmente nel novembre 2011 e nel 2014 Mojang è stata acquistata da Microsoft. È uno dei videogiochi "
     "più venduti di sempre."),
    ("Iron Man",
     "Iron Man, alter ego di Anthony Edward \"Tony\" Stark, è un personaggio dei fumetti creato da Stan Lee, "
     "Larry Lieber, Don Heck e Jack Kirby, apparso per la prima volta nel 1963 su Tales of Suspense n. 39, "
     "pubblicato dalla Marvel Comics. Nel Marvel Cinematic Universe è interpretato da Robert Downey Jr., a "
     "partire dal film Iron Man del 2008.",
     "Iron Man è Tony Stark, personaggio Marvel creato da Stan Lee, Larry Lieber, Don Heck e Jack Kirby{T}. "
     "Debuttò nel 1963 su Tales of Suspense numero 39, e al cinema è stato interpretato da Robert Downey Jr. "
     "a partire dal 2008. Un uomo con un eccellente gusto in fatto di assistenti."),
    ("Colosseo",
     "Il Colosseo, originariamente Anfiteatro Flavio, è il più grande anfiteatro romano del mondo, situato nel "
     "centro di Roma. Iniziato da Vespasiano intorno al 70-72 d.C. e inaugurato da Tito nell'80 d.C., poteva "
     "ospitare tra 50.000 e 87.000 spettatori. Nel 2007 è stato inserito tra le nuove sette meraviglie del mondo.",
     "Il Colosseo, in origine Anfiteatro Flavio, è il più grande anfiteatro romano mai costruito{T}. Iniziato "
     "da Vespasiano intorno al 70-72 dopo Cristo e inaugurato da Tito nell'80, poteva ospitare decine di "
     "migliaia di spettatori. Dal 2007 è tra le nuove sette meraviglie del mondo."),
    ("Monte Everest",
     "L'Everest è la montagna più alta della Terra, con 8.849 metri sul livello del mare secondo la misurazione "
     "del 2020. Si trova nella catena dell'Himalaya, al confine tra Nepal e Cina. La prima ascensione "
     "documentata fu compiuta il 29 maggio 1953 da Edmund Hillary e Tenzing Norgay.",
     "L'Everest è alto 8.849 metri, secondo la misurazione del 2020{T}. Si trova nell'Himalaya, al confine tra "
     "Nepal e Cina, e fu scalato per la prima volta il 29 maggio 1953 da Edmund Hillary e Tenzing Norgay."),
    ("Galileo Galilei",
     "Galileo Galilei (Pisa, 15 febbraio 1564 – Arcetri, 8 gennaio 1642) è stato un fisico, astronomo e "
     "filosofo italiano, considerato il padre della scienza moderna. Perfezionò il cannocchiale e scoprì "
     "quattro satelliti di Giove. Per aver sostenuto la teoria copernicana fu processato dall'Inquisizione nel 1633.",
     "Galileo Galilei, nato a Pisa nel 1564, è considerato il padre della scienza moderna{T}. Perfezionò il "
     "cannocchiale, scoprì quattro satelliti di Giove e, per aver difeso la teoria copernicana, fu processato "
     "dall'Inquisizione nel 1633. Morì ad Arcetri nel 1642."),
    ("Albert Einstein",
     "Albert Einstein (Ulma, 14 marzo 1879 – Princeton, 18 aprile 1955) è stato un fisico tedesco naturalizzato "
     "svizzero e statunitense. È noto soprattutto per la teoria della relatività e per l'equazione E = mc². Nel "
     "1921 ricevette il premio Nobel per la fisica per la spiegazione dell'effetto fotoelettrico.",
     "Albert Einstein, nato a Ulma nel 1879 e morto a Princeton nel 1955, è il fisico della teoria della "
     "relatività e di E = mc²{T}. Curiosamente, il Nobel del 1921 non gli fu dato per la relatività, ma per la "
     "spiegazione dell'effetto fotoelettrico."),
    ("Stephen Hawking",
     "Stephen William Hawking (Oxford, 8 gennaio 1942 – Cambridge, 14 marzo 2018) è stato un fisico, cosmologo "
     "e divulgatore scientifico britannico. Studiò i buchi neri e l'origine dell'universo e ipotizzò che i buchi "
     "neri emettano una radiazione, detta radiazione di Hawking. Colpito da una malattia del motoneurone, "
     "comunicava attraverso un sintetizzatore vocale.",
     "Stephen Hawking era un fisico e cosmologo britannico, vissuto dal 1942 al 2018{T}. Studiò i buchi neri e "
     "l'origine dell'universo, e scoprì che i buchi neri dovrebbero emettere una radiazione, che porta il suo "
     "nome. A causa di una malattia del motoneurone comunicava con un sintetizzatore vocale."),
    ("Leonardo da Vinci",
     "Leonardo di ser Piero da Vinci (Anchiano, 15 aprile 1452 – Amboise, 2 maggio 1519) è stato un pittore, "
     "ingegnere e scienziato italiano. È considerato uno dei più grandi geni dell'umanità. Tra le sue opere più "
     "celebri ci sono la Gioconda e l'Ultima Cena.",
     "Leonardo da Vinci, nato nel 1452 e morto ad Amboise nel 1519, fu pittore, ingegnere e scienziato{T}: uno "
     "dei più grandi geni della storia. Tra le sue opere più celebri ci sono la Gioconda e l'Ultima Cena."),
    ("Su Nuraxi",
     "Su Nuraxi è un complesso nuragico situato a Barumini, nel sud della Sardegna. La sua torre centrale "
     "risale all'età del Bronzo ed è circondata da un bastione e da un villaggio. Il sito fu riportato alla "
     "luce negli anni Cinquanta dall'archeologo Giovanni Lilliu. Dal 1997 è patrimonio mondiale dell'UNESCO.",
     "Su Nuraxi è il complesso nuragico di Barumini, nel sud della Sardegna{T}. La torre centrale risale all'età "
     "del Bronzo ed è circondata da un bastione e da un villaggio. Fu riportato alla luce negli anni Cinquanta "
     "da Giovanni Lilliu ed è patrimonio dell'UNESCO dal 1997."),
    ("Torre Eiffel",
     "La torre Eiffel è una torre di ferro alta circa 330 metri, situata a Parigi. Fu costruita su progetto "
     "dell'impresa di Gustave Eiffel per l'Esposizione universale del 1889. È uno dei monumenti più visitati al "
     "mondo.",
     "La torre Eiffel, a Parigi, è alta circa 330 metri ed è fatta di ferro{T}. Fu costruita dall'impresa di "
     "Gustave Eiffel per l'Esposizione universale del 1889: doveva essere temporanea, e invece eccola ancora lì."),
    ("Nikola Tesla",
     "Nikola Tesla (Smiljan, 10 luglio 1856 – New York, 7 gennaio 1943) è stato un inventore e ingegnere serbo "
     "naturalizzato statunitense. È noto per i suoi contributi allo sviluppo della corrente alternata e del "
     "motore a induzione. L'unità di misura dell'induzione magnetica, il tesla, porta il suo nome.",
     "Nikola Tesla era un inventore e ingegnere serbo, naturalizzato statunitense, vissuto dal 1856 al 1943{T}. "
     "Fu fondamentale per lo sviluppo della corrente alternata e del motore a induzione; in suo onore, l'unità "
     "di misura dell'induzione magnetica si chiama tesla."),
]
DOMANDE_WIKI = ["Cerca su Wikipedia {x}", "Controlla su Wikipedia chi era {x}", "Dammi informazioni precise su {x}",
                "Cosa dice Wikipedia su {x}?", "Verifica su Wikipedia: {x}"]


def dati_wikipedia(titolo, estratto):
    strumenti._scarica = lambda url, parametri=None: json.dumps({"query": {"pages": [{
        "title": titolo, "extract": estratto,
        "fullurl": "https://it.wikipedia.org/wiki/" + titolo.replace(" ", "_")}]}}).encode()
    return strumenti.wikipedia(titolo)


def esempi_wikipedia():
    esempi = []
    for titolo, estratto, risposta in VOCI:
        for domanda in caso.sample(DOMANDE_WIKI, 2):
            ctx = Contesto()
            esempi.append(esempio(ctx, [utente(domanda.format(x=titolo)), chiama(("wikipedia", {"argomento": titolo})),
                                        risultato(dati_wikipedia(titolo, estratto)), jarvis(risposta)]))
    for parola in ("xqzv", "Fluxomatic 3000"):
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(f"Cerca su Wikipedia {parola}"), chiama(("wikipedia", {"argomento": parola})),
                                    risultato(f'Errore: non trovo niente su Wikipedia per "{parola}".'),
                                    jarvis(f"Wikipedia non ha nulla su «{parola}»{{T}}. Forse si scrive in modo "
                                           "diverso? Me lo riscriva e riprovo.")]))
    return esempi


# --- Notizie -------------------------------------------------------------------------------

TITOLI = {
    "": ["Maltempo, allerta gialla in tre regioni per domani - ANSA",
         "Scuola, pubblicato il calendario delle prove Invalsi - Skuola.net",
         "Treni, sciopero nazionale venerdì: le fasce garantite - Corriere della Sera",
         "Musei statali, record di visitatori nel fine settimana - la Repubblica",
         "Benzina, prezzi in lieve calo questa settimana - Il Sole 24 Ore",
         "Spazio, completato il test del nuovo razzo europeo - Wired Italia",
         "Influenza, il picco è previsto tra due settimane - Adnkronos",
         "Città, più piste ciclabili nei centri storici - TGCom24"],
    "calcio": ["Serie A, il Cagliari vince in rimonta davanti al suo pubblico - L'Unione Sarda",
               "Champions League, stasera in campo le italiane - Sky Sport",
               "Calciomercato, le trattative del giorno - La Gazzetta dello Sport",
               "Nazionale, i convocati per le prossime amichevoli - Rai Sport",
               "Serie A, la classifica dopo l'ultima giornata - Corriere dello Sport"],
    "tecnologia": ["Schede video, annunciati i nuovi modelli di fascia media - HDblog",
                   "Intelligenza artificiale, le novità della settimana - Wired Italia",
                   "Smartphone, un aggiornamento promette più autonomia - Tom's Hardware",
                   "Truffe online, attenzione ai falsi SMS dei corrieri - Il Post",
                   "Windows, disponibile l'aggiornamento mensile di sicurezza - HTML.it"],
    "Minecraft": ["Minecraft, annunciato il prossimo aggiornamento con nuovi mob - Everyeye.it",
                  "Minecraft, i modpack più scaricati del mese - Multiplayer.it",
                  "Minecraft Live: tutte le novità presentate - IGN Italia",
                  "Minecraft, una scuola ricostruisce il proprio paese a blocchi - Il Post"],
    "Sardegna": ["Sardegna, nuovi collegamenti aerei per l'inverno - L'Unione Sarda",
                 "Cagliari, al via i lavori sul lungomare - Casteddu Online",
                 "Nuoro, un festival letterario dedicato a Grazia Deledda - La Nuova Sardegna",
                 "Olbia, cresce il numero di passeggeri al porto - Olbia.it"],
}
DOMANDE_NOTIZIE = {"": ["Quali sono le ultime notizie?", "Cosa succede nel mondo?", "Dimmi le notizie di oggi",
                        "Novità dal mondo?"],
                   "calcio": ["Novità sul calcio?", "Ultime notizie di calcio"],
                   "tecnologia": ["Ci sono notizie di tecnologia?", "Novità nel mondo della tecnologia?"],
                   "Minecraft": ["Ci sono notizie su Minecraft?", "Novità su Minecraft?"],
                   "Sardegna": ["Ultime notizie dalla Sardegna", "Cosa succede in Sardegna?"]}


def dati_notizie(ctx, argomento):
    scelti = caso.sample(TITOLI[argomento], min(len(TITOLI[argomento]), caso.choice([4, 5])))
    voci = "".join(f"<item><title>{t}</title><pubDate>{(ctx.adesso - timedelta(hours=i * 2 + 1)):%a, %d %b %Y %H:%M:%S} "
                   f"+0000</pubDate></item>" for i, t in enumerate(scelti))
    strumenti._scarica = lambda url, parametri=None: f"<rss><channel>{voci}</channel></rss>".encode()
    return strumenti.notizie(argomento), [t.rsplit(" - ", 1)[0] for t in scelti]


def risposta_notizie(argomento, titoli):
    inizio = (f"Ecco le ultime notizie su {argomento}{{T}}:" if argomento
              else caso.choice(["Ecco i titoli principali{T}:", "Le notizie più importanti del momento{T}:"]))
    elenco = "\n".join(f"- {t}" for t in titoli[:3])
    return f"{inizio}\n{elenco}\nVuole che approfondisca qualcosa?"


def esempi_notizie():
    esempi = []
    for argomento, numero in (("", 7), ("calcio", 3), ("tecnologia", 3), ("Minecraft", 3), ("Sardegna", 2)):
        for _ in range(numero):
            ctx = Contesto()
            testo, titoli = dati_notizie(ctx, argomento)
            argomenti = {"argomento": argomento} if argomento else {}
            esempi.append(esempio(ctx, [utente(caso.choice(DOMANDE_NOTIZIE[argomento])), chiama(("notizie", argomenti)),
                                        risultato(testo), jarvis(risposta_notizie(argomento, titoli))]))
    return esempi


# --- Calcoli -------------------------------------------------------------------------------

def esempi_calcoli():
    esempi = []
    modelli = [
        lambda a, b: (f"Quanto fa {a} per {b}?", f"{a}*{b}", "Fa {r}{T}."),
        lambda a, b: (f"Quanto fa {a * b} diviso {b}?", f"{a * b}/{b}", "Fa {r}{T}."),
        lambda a, b: (f"Quanto fa {a} più {b}?", f"{a}+{b}", "Fa {r}{T}."),
        lambda a, b: (f"Quanto è il {b}% di {a * 10}?", f"{a * 10}*{b}/100", "Il {b}% di {x} è {r}{T}."),
        lambda a, b: (f"Radice quadrata di {a * a}?", f"sqrt({a * a})", "La radice quadrata di {x} è {r}{T}."),
        lambda a, b: (f"Quanto fa {b % 9 + 2} alla {b % 5 + 2}?", f"{b % 9 + 2}^{b % 5 + 2}", "Fa {r}{T}."),
        lambda a, b: (f"Se compro {b % 7 + 2} biglietti da {a % 40 + 5},50 euro quanto spendo?",
                      f"{b % 7 + 2}*{a % 40 + 5}.5", "Spende {r} euro{T}."),
        lambda a, b: (f"Quanti secondi ci sono in {b % 9 + 2} ore?", f"{b % 9 + 2}*3600", "Sono {r} secondi{T}."),
        lambda a, b: (f"Quanto fa {a} meno {b}?", f"{a}-{b}", "Fa {r}{T}."),
        lambda a, b: (f"Calcola ({a} + {b}) * 3", f"({a} + {b}) * 3", "Il risultato è {r}{T}."),
    ]
    for i in range(40):
        a, b = caso.randrange(12, 999), caso.randrange(3, 99)
        domanda, espressione, risposta = modelli[i % len(modelli)](a, b)
        risultato_vero = strumenti.calcola(espressione)
        valore = risultato_vero.rsplit(" = ", 1)[1]
        x = espressione.split("*")[0] if "%" in domanda else espressione[5:-1] if "sqrt" in espressione else ""
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(domanda), chiama(("calcola", {"espressione": espressione})),
                                    risultato(risultato_vero),
                                    jarvis(risposta.format(r=valore, b=b, x=strumenti._numero(int(x)) if x else "", T="{T}"))]))
    return esempi


# --- Timer ---------------------------------------------------------------------------------

DURATE = [(0.5, "30 secondi"), (1, "un minuto"), (2, "2 minuti"), (3, "3 minuti"), (5, "5 minuti"),
          (10, "10 minuti"), (12, "12 minuti"), (15, "un quarto d'ora"), (20, "20 minuti"), (25, "25 minuti"),
          (30, "mezz'ora"), (45, "45 minuti"), (60, "un'ora"), (90, "un'ora e mezza")]
SCOPI = ["la pasta", "la pizza nel forno", "il bucato", "il tè", "le uova"]
AZIONI = ["chiamare la nonna", "spegnere il forno", "uscire", "ritirare il bucato", "fare una pausa"]


def risultato_timer(ctx, minuti):
    scadenza = ctx.adesso + timedelta(minutes=minuti)
    return f"Timer di {strumenti._durata(minuti)} impostato: suonerà alle {scadenza:%H:%M:%S}."


def esempi_timer():
    esempi = []
    for i in range(26):
        ctx = Contesto()
        minuti, parole = caso.choice(DURATE)
        alle = ore(ctx, minuti) if minuti >= 1 else f"{ctx.adesso + timedelta(minutes=minuti):%H:%M:%S}"
        forma = i % 4
        if forma == 0:
            scopo = caso.choice(SCOPI)
            domanda, argomenti = f"Metti un timer di {parole} per {scopo}", {"minuti": minuti, "messaggio": scopo}
            risposta = caso.choice([f"Fatto{{T}}: alle {alle} le dirò che {scopo} è pronta." if scopo in
                                    ("la pasta", "la pizza nel forno") else f"Fatto{{T}}: la avviserò alle {alle}.",
                                    f"Timer impostato{{T}}. Alle {alle} le ricorderò {scopo}."])
        elif forma == 1:
            azione = caso.choice(AZIONI)
            domanda, argomenti = f"Ricordami tra {parole} di {azione}", {"minuti": minuti, "messaggio": azione}
            risposta = f"D'accordo{{T}}: alle {alle} le ricorderò di {azione}."
        elif forma == 2:
            domanda, argomenti = caso.choice([f"Avvisami tra {parole}", f"Timer di {parole}"]), {"minuti": minuti}
            risposta = caso.choice([f"Fatto{{T}}: la avviserò alle {alle}.", f"Timer impostato{{T}}: suonerà alle {alle}."])
        else:
            domanda = "Facciamo 25 minuti di studio, poi avvisami"
            minuti, alle = 25, ore(ctx, 25)
            argomenti = {"minuti": 25, "messaggio": "pausa dallo studio"}
            risposta = f"Si comincia{{T}}: alle {alle} le dirò che è ora di una pausa. Buono studio."
        esempi.append(esempio(ctx, [utente(domanda), chiama(("timer", argomenti)),
                                    risultato(risultato_timer(ctx, minuti)), jarvis(risposta)]))
    return esempi


# --- Siti, ricerche e programmi ------------------------------------------------------------

SITI = {"YouTube": "youtube.com", "Google": "google.com", "Wikipedia": "it.wikipedia.org", "Netflix": "netflix.com",
        "Twitch": "twitch.tv", "CurseForge": "curseforge.com", "Modrinth": "modrinth.com", "GitHub": "github.com",
        "Spotify": "open.spotify.com", "Instagram": "instagram.com", "Gmail": "mail.google.com",
        "Amazon": "amazon.it", "Google Classroom": "classroom.google.com", "Google Maps": "maps.google.com"}
RICERCHE = ["ricette di pasta al forno", "migliori modpack Minecraft", "orari treni Cagliari Sassari",
            "come fare il nodo alla cravatta", "esercizi di inglese sul present perfect", "film al cinema stasera",
            "trucchi per Minecraft", "come pulire la tastiera"]
PROGRAMMI = {"blocco note": "il Blocco note", "calcolatrice": "la Calcolatrice", "paint": "Paint",
             "esplora file": "Esplora file", "impostazioni": "le Impostazioni"}


def esempi_aperture():
    esempi = []
    strumenti.webbrowser.open = lambda indirizzo: True
    strumenti.os.startfile = lambda percorso: None
    for i, (nome, dominio) in enumerate(list(SITI.items()) * 2):
        ctx = Contesto()
        domanda = caso.choice(["Apri {s}", "Mi apri {s}?", "Vai su {s}", "Portami su {s}", "Apri {s} per favore"])
        saluto = " Buona visione." if nome in ("YouTube", "Netflix", "Twitch") else ""
        risposta = caso.choice([f"Ecco {nome}{{T}}.{saluto}", f"{nome} è aperto nel browser{{T}}.",
                                f"Fatto{{T}}: {nome} è aperto.{saluto}"])
        esempi.append(esempio(ctx, [utente(domanda.format(s=nome)), chiama(("apri_sito", {"indirizzo": dominio})),
                                    risultato(strumenti.apri_sito(dominio)), jarvis(risposta)]))
        if i >= 20:
            break
    for testo in RICERCHE + caso.sample(RICERCHE, 4):
        ctx = Contesto()
        domanda = caso.choice(["Cerca su Google {q}", "Fammi una ricerca su {q}", "Cercami {q}", "Cerca {q} su internet"])
        esempi.append(esempio(ctx, [utente(domanda.format(q=testo)), chiama(("cerca_sul_web", {"testo": testo})),
                                    risultato(strumenti.cerca_sul_web(testo)),
                                    jarvis(caso.choice([f"Ho aperto la ricerca di «{testo}» nel browser{{T}}.",
                                                        f"Ecco i risultati per «{testo}»{{T}}: li trova nel browser."]))]))
    for nome, con_articolo in list(PROGRAMMI.items()) * 3:
        ctx = Contesto()
        domanda = caso.choice([f"Apri {con_articolo.lower() if con_articolo[0] in 'il' else con_articolo}",
                               f"Mi apri {nome}?", f"Apri {nome}"])
        esempi.append(esempio(ctx, [utente(domanda), chiama(("apri_programma", {"nome": nome})),
                                    risultato(strumenti.apri_programma(nome, ctx.config["programmi"])),
                                    jarvis(f"Ecco {con_articolo}{{T}}.")]))
    for programma in ("Photoshop", "Discord", "Steam", "Word", "Fortnite"):
        ctx = Contesto()
        errore = strumenti.esegui("apri_programma", {"nome": programma}, ctx.config, print)
        esempi.append(esempio(ctx, [utente(f"Apri {programma}"), chiama(("apri_programma", {"nome": programma})),
                                    risultato(errore),
                                    jarvis(f"{programma} non è tra i programmi che posso aprire{{T}}. Può aggiungerlo "
                                           "in config.json, alla voce programmi, con il percorso del programma: da "
                                           "quel momento basterà chiedermelo.")]))
    return esempi


# --- Diagnostica e multimedia -------------------------------------------------------------

def dati_diagnostica(ctx):
    d = {"core": caso.choice([6, 8, 12, 16]), "ore": caso.randrange(0, 120), "minuti": caso.randrange(60),
         "ram_tot": caso.choice([8.0, 16.0, 32.0]), "disco_tot": caso.choice([476, 931, 1863]),
         "temp": caso.randrange(33, 86), "uso": caso.randrange(0, 100), "vram_tot": 6.0}
    d["ram"] = d["ram_tot"] * caso.uniform(0.25, 0.95)
    d["disco"] = caso.choice([caso.randrange(5, 20), caso.randrange(40, 400)])
    d["vram"] = caso.uniform(0.3, 5.8)
    d["batteria"] = (caso.randrange(5, 100), caso.random() < 0.5) if caso.random() < 0.25 else None
    righe = [f"Diagnostica del sistema ({ctx.adesso:%d/%m/%Y %H:%M})",
             f"Sistema: Windows 11, processore con {d['core']} core.",
             f"Acceso da: {d['ore']} ore e {d['minuti']} minuti.",
             f"Memoria RAM: {strumenti._gb(d['ram'])} usati su {strumenti._gb(d['ram_tot'])} "
             f"({d['ram'] / d['ram_tot']:.0%}).",
             f"Disco C:\\: {d['disco']} GB liberi su {d['disco_tot']} GB.",
             f"Scheda video NVIDIA GeForce RTX 3050: {strumenti._gb(d['vram'])} usati su "
             f"{strumenti._gb(d['vram_tot'])}, temperatura {d['temp']}°C, utilizzo {d['uso']}%."]
    if d["batteria"]:
        righe.append(f"Batteria: {d['batteria'][0]}%{' (in carica)' if d['batteria'][1] else ''}.")
    return "\n".join(righe), d


def risposta_diagnostica(tipo, d):
    ram = round(d["ram"] / d["ram_tot"] * 100)
    if tipo == "ram":
        return f"Sta usando {strumenti._gb(d['ram'])} di RAM su {strumenti._gb(d['ram_tot'])}{{T}}, il {ram}%."
    if tipo == "disco":
        nota = " Comincia a scarseggiare: una pulizia non guasterebbe." if d["disco"] < 20 else ""
        return f"Sul disco C ci sono {d['disco']} GB liberi su {d['disco_tot']}{{T}}.{nota}"
    if tipo == "temperatura":
        nota = (" È piuttosto calda: se sta giocando è normale, altrimenti controlli le ventole." if d["temp"] >= 80
                else " Tutto nella norma.")
        return f"La scheda video è a {d['temp']} gradi{{T}}, con un utilizzo del {d['uso']}%.{nota}"
    problemi = []
    if ram >= 85:
        problemi.append("la memoria è quasi piena: chiudere qualche programma aiuterebbe")
    if d["disco"] < 20:
        problemi.append(f"sul disco restano solo {d['disco']} GB: le suggerirei una pulizia")
    if d["temp"] >= 80:
        problemi.append(f"la scheda video è a {d['temp']} gradi, piuttosto calda")
    if d["batteria"] and d["batteria"][0] <= 20 and not d["batteria"][1]:
        problemi.append(f"la batteria è al {d['batteria'][0]}%: le conviene collegare il caricabatterie")
    if d["ore"] >= 72:
        problemi.append(f"il PC è acceso da {d['ore']} ore: un riavvio ogni tanto non guasta")
    sintesi = (f"Diagnostica completata{{T}}. Memoria al {ram}%, {d['disco']} GB liberi sul disco, scheda video a "
               f"{d['temp']} gradi con {strumenti._gb(d['vram'])} di memoria occupati.")
    if not problemi:
        return sintesi + " Tutti i sistemi sono nella norma."
    return sintesi + "\nDa segnalare:\n" + "\n".join(f"- {p}" for p in problemi)


DOMANDE_DIAGNOSTICA = {"tutto": ["Fai una diagnostica del sistema", "Come sta il PC?", "Stato del sistema",
                                 "Jarvis, diagnostica completa", "Controlla il computer"],
                       "ram": ["Quanta RAM sto usando?", "Com'è messa la memoria?"],
                       "disco": ["Quanto spazio ho sul disco?", "Ho ancora spazio sul PC?"],
                       "temperatura": ["Che temperatura ha la scheda video?", "La scheda video scalda?"]}
FRASI_MULTIMEDIA = {
    "alza_volume": (["Alza il volume", "Più forte", "Alza un po' la musica"], ["Volume alzato{T}.", "Fatto{T}: più forte."]),
    "abbassa_volume": (["Abbassa il volume", "Abbassa un po'", "Più piano"], ["Volume abbassato{T}.", "Fatto{T}: più piano."]),
    "muto": (["Togli l'audio", "Metti muto", "Disattiva l'audio"], ["Audio disattivato{T}.", "Fatto{T}: muto."]),
    "play_pausa": (["Metti in pausa la musica", "Pausa", "Fai ripartire la musica"], ["Fatto{T}.", "Eseguito{T}."]),
    "successiva": (["Prossima canzone", "Salta questa canzone", "Canzone successiva"],
                   ["Passo alla prossima{T}.", "Fatto{T}: traccia successiva."]),
    "precedente": (["Canzone precedente", "Torna alla canzone di prima"], ["Torno alla precedente{T}.", "Fatto{T}."]),
}


def esempi_pc():
    esempi = []
    for tipo, numero in (("tutto", 7), ("ram", 2), ("disco", 2), ("temperatura", 2)):
        for _ in range(numero):
            ctx = Contesto()
            testo, d = dati_diagnostica(ctx)
            esempi.append(esempio(ctx, [utente(caso.choice(DOMANDE_DIAGNOSTICA[tipo])), chiama(("diagnostica", {})),
                                        risultato(testo), jarvis(risposta_diagnostica(tipo, d))]))
    for azione, (domande, risposte) in FRASI_MULTIMEDIA.items():
        for domanda in domande:
            ctx = Contesto()
            esempi.append(esempio(ctx, [utente(domanda), chiama(("multimedia", {"azione": azione})),
                                        risultato(strumenti._TASTI[azione][2]), jarvis(caso.choice(risposte))]))
    return esempi


# --- Più strumenti insieme, domande di seguito, comandi -----------------------------------

def esempi_combinati():
    esempi = []
    for _ in range(4):
        ctx = Contesto()
        c1, c2 = caso.sample(list(CITTA), 2)
        (t1, d1), (t2, d2) = dati_meteo(ctx, c1), dati_meteo(ctx, c2)
        a1, a2 = d1["adesso"], d2["adesso"]
        esempi.append(esempio(ctx, [
            utente(f"Che tempo fa a {c1} e a {c2}?"),
            chiama(("meteo", {"citta": c1}), ("meteo", {"citta": c2})), risultato(t1), risultato(t2),
            jarvis(f"A {c1} ci sono {g(a1['temp'])} gradi e {FRASE_CIELO[a1['codice']]}{{T}}; a {c2} "
                   f"{g(a2['temp'])} gradi e {FRASE_CIELO[a2['codice']]}.")]))
    for _ in range(2):
        ctx = Contesto()
        minuti = caso.choice([20, 30, 45])
        esempi.append(esempio(ctx, [
            utente(f"Apri YouTube e metti un timer di {minuti} minuti"),
            chiama(("apri_sito", {"indirizzo": "youtube.com"}), ("timer", {"minuti": minuti})),
            risultato(strumenti.apri_sito("youtube.com")), risultato(risultato_timer(ctx, minuti)),
            jarvis(f"Ecco YouTube{{T}}, e il timer suonerà alle {ore(ctx, minuti)}. Buona visione.")]))
    ctx = Contesto()
    esempi.append(esempio(ctx, [
        utente("Alza il volume e passa alla prossima canzone"),
        chiama(("multimedia", {"azione": "alza_volume"}), ("multimedia", {"azione": "successiva"})),
        risultato(strumenti._TASTI["alza_volume"][2]), risultato(strumenti._TASTI["successiva"][2]),
        jarvis("Fatto{T}: volume più alto e traccia successiva.")]))

    # Domande che seguono una risposta precedente (in cronologia restano solo i testi).
    for _ in range(4):
        ctx = Contesto()
        c1, c2 = caso.sample(list(CITTA), 2)
        _, d1 = dati_meteo(ctx, c1)
        t2, d2 = dati_meteo(ctx, c2)
        esempi.append(esempio(ctx, [
            utente(f"Che tempo fa a {c1}?"), jarvis(risposta_meteo("adesso", c1, d1)),
            utente(f"E a {c2}?"), chiama(("meteo", {"citta": c2})), risultato(t2),
            jarvis(risposta_meteo("adesso", c2, d2))]))
    for _ in range(3):
        ctx = Contesto()
        a, b, c = caso.randrange(11, 99), caso.randrange(11, 99), caso.choice([2, 3, 4, 5])
        primo = strumenti.calcola(f"{a}*{b}").rsplit(" = ", 1)[1]
        secondo = strumenti.calcola(f"{a * b}/{c}")
        esempi.append(esempio(ctx, [
            utente(f"Quanto fa {a} per {b}?"), jarvis(f"Fa {primo}{{T}}."),
            utente(f"E diviso {c}?"), chiama(("calcola", {"espressione": f"{a * b}/{c}"})), risultato(secondo),
            jarvis(f"Fa {secondo.rsplit(' = ', 1)[1]}{{T}}.")]))
    ctx = Contesto()
    esempi.append(esempio(ctx, [utente("Apri YouTube"), jarvis("Ecco YouTube{T}. Buona visione."),
                                utente("Grazie"), jarvis("È un piacere{T}.")]))

    # Domande arrivate da /meteo, /wiki e /notizie: i dati sono già nel messaggio, niente strumenti.
    for _ in range(6):
        ctx, citta = Contesto(), caso.choice(list(CITTA))
        testo, dati = dati_meteo(ctx, citta)
        esempi.append(esempio(ctx, [utente(f"Che tempo fa a {citta}?{cervello.SEPARATORE_DATI}{testo}"),
                                    jarvis(risposta_meteo(caso.choice(["adesso", "tre_giorni"]), citta, dati))],
                              con_strumenti=False))
    for titolo, estratto, risposta in caso.sample(VOCI, 5):
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(f"Parlami di {titolo}.{cervello.SEPARATORE_DATI}"
                                           f"{dati_wikipedia(titolo, estratto)}"), jarvis(risposta)],
                              con_strumenti=False))
    for _ in range(4):
        ctx = Contesto()
        testo, titoli = dati_notizie(ctx, "")
        esempi.append(esempio(ctx, [utente(f"Quali sono le ultime notizie?{cervello.SEPARATORE_DATI}{testo}"),
                                    jarvis(risposta_notizie("", titoli))], con_strumenti=False))
    return esempi


# --- Memoria, data e ora, saluti, se stesso ----------------------------------------------

DOMANDE_MEMORIA = {
    "Il mio gioco preferito è Minecraft": ("Qual è il mio gioco preferito?", "Minecraft{T}, naturalmente."),
    "Venerdì ho la verifica di matematica": ("Quando ho la verifica di matematica?",
                                             "Venerdì{T}. Se vuole, possiamo ripassare insieme."),
    "Il mio colore preferito è il blu": ("Ti ricordi il mio colore preferito?", "Il blu{T}."),
    "Il mio cane si chiama Briciola": ("Come si chiama il mio cane?", "Briciola{T}."),
    "Tifo per il Cagliari": ("Per che squadra tifo?", "Per il Cagliari{T}."),
    "Gioco a Minecraft con un amico che vive in Piemonte": (
        "Dove vive l'amico con cui gioco?", "In Piemonte{T}: è l'amico con cui gioca a Minecraft."),
    "Mi piace la pizza margherita": ("Cosa mi piace mangiare?", "Da quanto mi risulta, la pizza margherita{T}."),
    "Studio al liceo scientifico": ("Che scuola faccio?", "Il liceo scientifico{T}."),
    "Mi alzo alle 7 per andare a scuola": ("A che ora mi alzo per la scuola?", "Alle 7{T}."),
}
RICORDATI = [
    ("Ricordati che il mio gioco preferito è Minecraft", "Annotato{T}: il suo gioco preferito è Minecraft."),
    ("Ricordati che venerdì ho la verifica di matematica", "Annotato{T}. Se vuole, giovedì possiamo fare un ripasso."),
    ("Ricordati che il mio cane si chiama Briciola", "Memorizzato{T}: Briciola. Un nome adorabile."),
    ("Ricordati che tifo per il Cagliari", "Annotato{T}. Seguirò i risultati con particolare interesse."),
    ("Ricordati che sono allergico alle arachidi",
     "Annotato{T}: niente arachidi. È il genere di informazione che conviene non dimenticare."),
    ("Ricordati che il compleanno di mia mamma è il 12 marzo",
     "Annotato{T}: il 12 marzo, compleanno di sua madre. Quando me lo chiederà, saprò dirglielo."),
    ("Ricordati che il mio colore preferito è il blu", "Memorizzato{T}: il blu."),
    ("Ricordati che gioco a Minecraft con un amico in Piemonte",
     "Annotato{T}: il suo compagno di partite è in Piemonte."),
]


def esempi_memoria():
    esempi = []
    for domanda, risposta in RICORDATI:
        esempi.append(esempio(Contesto(), [utente(domanda), jarvis(risposta)]))
    for fatto, (domanda, risposta) in DOMANDE_MEMORIA.items():
        for _ in range(2):
            altri = [f for f, _ in caso.sample(FATTI, 2) if f != fatto]
            esempi.append(esempio(Contesto(fatti=altri + [fatto]), [utente(domanda), jarvis(risposta)]))
    for domanda in ("Qual è il mio film preferito?", "Come si chiama mia sorella?", "Qual è il mio numero preferito?"):
        ctx = Contesto(fatti=[f for f, _ in caso.sample(FATTI, 2)])
        esempi.append(esempio(ctx, [utente(domanda),
                                    jarvis("Non me l'ha mai detto{T}. Se vuole, me lo dica e lo terrò a mente.")]))
    for _ in range(4):
        scelti = caso.sample(FATTI, 3)
        ctx = Contesto(fatti=[f for f, _ in scelti])
        elenco = "\n".join(f"- {seconda}" for _, seconda in scelti)
        esempi.append(esempio(ctx, [utente(caso.choice(["Cosa ti ricordi di me?", "Cosa sai di me?"])),
                                    jarvis(f"Ecco cosa ho in memoria{{T}}:\n{elenco}")]))
    ctx = Contesto(fatti=[])
    esempi.append(esempio(ctx, [utente("Cosa sai di me?"),
                                jarvis("Per ora nulla{T}: non mi ha ancora chiesto di ricordare niente. Basta dirmi "
                                       "\"ricordati che...\" e lo terrò a mente, anche dopo la chiusura.")]))
    return esempi


def saluto(ctx):
    ora = ctx.adesso.hour
    return "Buongiorno" if 5 <= ora < 12 else "Buon pomeriggio" if ora < 18 else "Buonasera"


def esempi_tempo_e_saluti():
    esempi = []
    for _ in range(5):
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(caso.choice(["Che giorno è oggi?", "Che giorno è?", "Oggi che data è?"])),
                                    jarvis(f"Oggi è {strumenti.data_italiana(ctx.adesso)}{{T}}.")]))
    for _ in range(5):
        ctx = Contesto()
        esempi.append(esempio(ctx, [utente(caso.choice(["Che ore sono?", "Che ora è?", "Mi dici l'ora?"])),
                                    jarvis(f"Sono le {ore(ctx)}{{T}}.")]))
    for _ in range(4):
        ctx = Contesto()
        natale = date(ctx.adesso.year, 12, 25)
        if natale < ctx.adesso.date():
            natale = date(ctx.adesso.year + 1, 12, 25)
        giorni = (natale - ctx.adesso.date()).days
        risposta = ("È oggi{T}! Buon Natale." if giorni == 0 else "È domani{T}!" if giorni == 1
                    else f"Mancano {giorni} giorni a Natale{{T}}.")
        esempi.append(esempio(ctx, [utente("Quanti giorni mancano a Natale?"), jarvis(risposta)]))
    for _ in range(3):
        ctx = Contesto()
        n = caso.choice([3, 7, 10, 30, 100])
        esempi.append(esempio(ctx, [utente(f"Che giorno sarà tra {n} giorni?"),
                                    jarvis(f"Tra {n} giorni sarà {strumenti.data_italiana(ctx.adesso + timedelta(days=n))}{{T}}.")]))
    for _ in range(14):
        ctx = Contesto()
        ora = ctx.adesso.hour
        domanda = caso.choice(["Buongiorno Jarvis", "Ciao Jarvis", "Eccomi", "Ehi Jarvis", "Buonasera Jarvis"])
        if 0 <= ora < 5:
            risposta = (f"Buonasera{{T}}, o forse dovrei dire buonanotte: sono le {ore(ctx)}. Posso aiutarla con "
                        "qualcosa prima che vada a dormire?")
        elif domanda == "Buongiorno Jarvis" and ora >= 18:
            risposta = f"Buonasera, piuttosto{{T}}: sono le {ore(ctx)}. Ma apprezzo l'ottimismo. Come posso aiutarla?"
        elif domanda == "Buonasera Jarvis" and ora < 12:
            risposta = f"Buongiorno{{T}}: sono solo le {ore(ctx)}, la sera è ancora lontana. Come posso aiutarla?"
        else:
            risposta = f"{saluto(ctx)}{{T}}. Sono le {ore(ctx)} di {strumenti.GIORNI[ctx.adesso.weekday()]}: come posso esserle utile?"
            if 5 <= ora < 10 and ctx.citta:
                risposta = (f"{saluto(ctx)}{{T}}. Sono le {ore(ctx)} di {strumenti.GIORNI[ctx.adesso.weekday()]}. "
                            f"Vuole che controlli il meteo a {ctx.citta}?")
        esempi.append(esempio(ctx, [utente(domanda), jarvis(risposta)]))
    return esempi


def esempi_se_stesso():
    capacita = ("Ecco cosa posso fare{T}:\n"
                "- rispondere alle domande e aiutarla con lo studio;\n"
                "- controllare meteo, notizie e Wikipedia;\n"
                "- aprire siti, ricerche e programmi;\n"
                "- fare calcoli esatti e impostare timer;\n"
                "- controllare lo stato del PC, il volume e la musica;\n"
                "- ricordare ciò che mi chiede, anche dopo la chiusura.\n"
                "Cosa le serve?")
    limiti = ("Ne ho diversi{T}:\n"
              "- non sento la voce e non vedo lo schermo;\n"
              "- non leggo né modifico file;\n"
              "- le mie conoscenze si fermano al mio addestramento: per le cose recenti uso gli strumenti;\n"
              "- sono un modello piccolo e posso sbagliare, quindi per le cose importanti è meglio controllare.")
    coppie = [("Cosa sai fare?", capacita), ("Cosa puoi fare per me?", capacita), ("Che funzioni hai?", capacita),
              ("Quali sono i tuoi limiti?", limiti), ("Cosa non sai fare?", limiti),
              ("Chi sei?", "Sono Jarvis, il suo assistente personale{T}. Funziono interamente sul suo PC, con un "
                           "modello linguistico addestrato su misura: rispondo alle domande, cerco informazioni, "
                           "apro programmi, imposto timer e tengo d'occhio il sistema."),
              ("Che modello sei?", f"Sono il modello {MODELLO}, e giro tramite Ollama interamente sul suo PC{{T}}."),
              ("Usi internet?", "Solo per meteo, notizie e Wikipedia, e solo quando servono{T}. Per pensare non ne "
                                "ho bisogno: il modello gira sul suo PC, e le conversazioni restano lì.")]
    esempi = [esempio(Contesto(), [utente(d), jarvis(r)]) for d, r in coppie for _ in range(2)]
    # Quando l'utente cambia appellativo o forma, Jarvis aggiorna config.json prima di rispondere:
    # il prompt di sistema contiene già la scelta nuova.
    for domanda, titolo, dai_del, risposta in [
        ("Chiamami capo", "capo", "lei", "Come desidera, capo."),
        ("Jarvis, chiamami comandante", "comandante", "lei", "Ricevuto, comandante. Da ora la chiamerò così."),
        ("Chiamami signore", "signore", "lei", "Come desidera, signore."),
        ("Non chiamarmi più signore", "", "lei", "Come preferisce. Niente più appellativi."),
        ("Dammi del tu", "", "tu", "D'accordo, da ora ti do del tu. Come posso aiutarti?"),
        ("Dammi pure del tu", "capo", "tu", "Va bene, capo: da ora ti do del tu."),
        ("Dammi del lei", "signore", "lei", "Come desidera, signore. Da ora le do del lei."),
    ]:
        ctx = Contesto()
        ctx.titolo = ctx.config["come_chiamarmi"] = titolo
        ctx.config["dai_del"] = dai_del
        esempi.append(esempio(ctx, [utente(domanda), jarvis(risposta)]))
    return esempi


# Domande da passare a Claude: il modello locale chiama lo strumento e Claude risponde all'utente.
DOMANDE_DIFFICILI = [
    ("Scrivimi un programma Python che ordina una lista di numeri senza usare sort", "programmazione"),
    ("Spiegami la relatività generale in modo approfondito", "spiegazione lunga e complessa"),
    ("Aiutami a scrivere un tema di due pagine sull'inquinamento", "compito di scuola lungo"),
    ("Un treno parte da Roma alle 8 a 120 km/h, un altro da Milano alle 9 a 150 km/h: quando si incontrano "
     "se sono a 570 km di distanza?", "problema di matematica a più passaggi"),
    ("Dimostrami che la radice quadrata di 2 è irrazionale", "dimostrazione matematica"),
    ("Devo scegliere tra liceo scientifico e istituto tecnico informatico: aiutami a decidere",
     "consiglio importante"),
    ("Trova l'errore in questo codice: for i in range(10) print(i)", "programmazione"),
    ("Mi spieghi le cause della Prima guerra mondiale con tutti i dettagli", "spiegazione lunga e complessa"),
    ("Come posso creare una mod per Minecraft?", "programmazione"),
    ("Analizza i pro e i contro dell'energia nucleare", "ragionamento lungo"),
    ("Risolvi l'equazione x^2 - 5x + 6 = 0 spiegando i passaggi", "problema di matematica a più passaggi"),
    ("Scrivi una lettera formale per chiedere uno stage", "testo lungo"),
]


def esempi_cervello_avanzato():
    esempi = []
    for domanda, motivo in DOMANDE_DIFFICILI:
        for _ in range(2):
            ctx = Contesto()
            esempi.append(esempio(ctx, [
                utente(domanda), chiama(("chiedi_al_cervello_avanzato", {"motivo": motivo})),
                risultato("Il cervello avanzato ha risposto direttamente all'utente."), jarvis("Fatto{T}.")]))
    return esempi


def esempi_dialoghi():
    esempi = []
    for domanda, risposta in CONVERSAZIONI:
        for _ in range(2):
            esempi.append(esempio(Contesto(), [utente(domanda), jarvis(risposta)]))
    for conversazione in CONVERSAZIONI_LUNGHE:
        for _ in range(2):
            esempi.append(esempio(Contesto(), [{"role": r, "content": t} for r, t in conversazione]))
    return esempi


# --- Controlli e scrittura ----------------------------------------------------------------

def controlla(e):
    """Verifica che ogni esempio sia coerente con quello che Jarvis manda davvero a Ollama."""
    nomi = {t["function"]["name"]: t["function"]["parameters"]
            for t in strumenti.schemi(cervello.CONFIG_PREDEFINITA) + [cervello.STRUMENTO_AVANZATO]}
    messaggi = e["messages"]
    assert messaggi[0]["role"] == "system" and messaggi[-1]["role"] == "assistant"
    attese = 0
    for m in messaggi[1:]:
        if m["role"] == "tool":
            assert attese > 0, "risultato senza chiamata"
            attese -= 1
            continue
        assert attese == 0, "chiamata senza risultato"
        if m.get("tool_calls"):
            assert e["tools"], "chiamata a uno strumento in un esempio senza strumenti"
            for c in m["tool_calls"]:
                nome, argomenti = c["function"]["name"], c["function"]["arguments"]
                assert nome in nomi, nome
                assert set(nomi[nome]["required"]) <= set(argomenti) <= set(nomi[nome]["properties"]), (nome, argomenti)
            attese = len(m["tool_calls"])
        elif m["role"] == "assistant":
            assert m["content"].strip() and "{T}" not in m["content"] and "**" not in m["content"], m["content"]
            assert not any(cervello._emoji(c) for c in m["content"]), m["content"]
    assert attese == 0


def main():
    gruppi = {
        "dialoghi": esempi_dialoghi(), "meteo": esempi_meteo(), "wikipedia": esempi_wikipedia(),
        "notizie": esempi_notizie(), "calcoli": esempi_calcoli(), "timer": esempi_timer(),
        "siti e programmi": esempi_aperture(), "PC": esempi_pc(), "combinati": esempi_combinati(),
        "memoria": esempi_memoria(), "cervello avanzato": esempi_cervello_avanzato(), "data, ora e saluti": esempi_tempo_e_saluti(), "se stesso": esempi_se_stesso(),
    }
    tutti = [e for gruppo in gruppi.values() for e in gruppo]
    for e in tutti:
        controlla(e)
    caso.shuffle(tutti)
    with open(FILE_DATASET, "w", encoding="utf-8") as f:
        for e in tutti:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    for nome, gruppo in gruppi.items():
        print(f"{nome:20} {len(gruppo):4}")
    lunghezze = [len(json.dumps(e, ensure_ascii=False)) for e in tutti]
    print(f"{'totale':20} {len(tutti):4} esempi, il più lungo circa {max(lunghezze) // 3} token")
    print(f"Salvato in {FILE_DATASET}")


if __name__ == "__main__":
    main()
