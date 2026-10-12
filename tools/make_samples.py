"""Generate synthetic accident statements and car order forms, with their ground truth.

Every person, company, plate, VIN and policy number here is invented. The documents
only mimic the structure of the real forms, so teams can test the pipeline end to end.

    uv run --group samples python tools/make_samples.py
"""

from __future__ import annotations

import io
import json
import random
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageFilter
from reportlab.lib.colors import Color, HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
TRUTH = ROOT / "ground_truth"
HAND = "Hand"
pdfmetrics.registerFont(TTFont(HAND, str(ROOT / "tools/fonts/HomemadeApple.ttf")))
INK = HexColor("#1b2a8a")
W, H = A4
SPECIMEN = "SPECIMEN - synthetic test document, all data is fictitious"

CIRCUMSTANCES = [
    "parked_or_stopped",
    "leaving_parking_or_opening_door",
    "entering_parking",
    "emerging_from_car_park_or_private_ground",
    "entering_car_park_or_private_ground",
    "entering_roundabout",
    "circulating_in_roundabout",
    "struck_rear_same_direction_same_lane",
    "same_direction_different_lane",
    "changing_lanes",
    "overtaking",
    "turning_right",
    "turning_left",
    "reversing",
    "encroaching_opposite_lane",
    "coming_from_right_at_intersection",
    "ignored_priority_sign_or_red_light",
]
CIRC_LABELS = {
    "fr": [
        "en stationnement / à l'arrêt",
        "quittait un stationnement / ouvrait une portière",
        "prenait un stationnement",
        "sortait d'un parking, d'un lieu privé, d'un chemin de terre",
        "s'engageait dans un parking, un lieu privé, un chemin de terre",
        "s'engageait sur une place à sens giratoire",
        "roulait sur une place à sens giratoire",
        "heurtait à l'arrière, en roulant dans le même sens et sur une même file",
        "roulait dans le même sens et sur une file différente",
        "changeait de file",
        "doublait",
        "virait à droite",
        "virait à gauche",
        "reculait",
        "empiétait sur une voie réservée à la circulation en sens inverse",
        "venait de droite (dans un carrefour)",
        "n'avait pas observé un signal de priorité ou un feu rouge",
    ],
    "nl": [
        "stond geparkeerd / stond stil",
        "verliet een parkeerplaats / opende een portier",
        "ging parkeren",
        "verliet een parking, een privé-terrein, een veldweg",
        "reed een parking, een privé-terrein, een veldweg op",
        "reed een rotonde op",
        "reed op een rotonde",
        "reed achteraan in op een voertuig in dezelfde richting en op dezelfde rijstrook",
        "reed in dezelfde richting maar op een andere rijstrook",
        "veranderde van rijstrook",
        "haalde in",
        "sloeg rechtsaf",
        "sloeg linksaf",
        "reed achteruit",
        "kwam op een rijbaan bestemd voor tegenliggers",
        "kwam van rechts (op een kruispunt)",
        "had een voorrangsteken of rood licht niet opgemerkt",
    ],
}
IMPACT_POINTS = ["front", "front_left", "front_right", "left_side", "right_side", "rear", "rear_left", "rear_right"]

LABELS = {
    "fr": {
        "title": "CONSTAT EUROPÉEN D'ACCIDENT",
        "sub": "À signer obligatoirement par les deux conducteurs. Ne constitue pas une reconnaissance de responsabilité.",
        "date": "1. Date de l'accident", "time": "Heure", "place": "2. Lieu (pays, localité, rue)",
        "injuries": "3. Blessé(s) même léger(s)", "damage": "4. Dégâts matériels autres qu'aux véhicules A et B",
        "witnesses": "5. Témoins: noms, adresses, tél.", "yes": "oui", "no": "non",
        "holder": "6. Preneur d'assurance / assuré", "vehicle": "7. Véhicule", "insurer": "8. Société d'assurance",
        "driver": "9. Conducteur", "impact": "10. Point de choc initial", "visible": "11. Dégâts apparents",
        "circ": "12. Circonstances", "sketch": "13. Croquis de l'accident au moment du choc",
        "remarks": "14. Mes observations", "sign": "15. Signature des conducteurs",
        "name": "Nom", "first": "Prénom", "address": "Adresse", "pc": "Code postal", "country": "Pays",
        "phone": "Tél. ou e-mail", "make": "Marque, type", "plate": "N° d'immatriculation",
        "reg": "Pays d'immatriculation", "company": "Nom", "policy": "N° de contrat",
        "green": "N° de carte verte", "valid": "Valable du / au", "agency": "Agence (ou bureau, courtier)",
        "birth": "Date de naissance", "licence": "Permis de conduire n°", "cat": "Catégorie",
        "until": "Valable jusqu'au", "count": "Nombre de cases marquées", "veh_a": "VÉHICULE A", "veh_b": "VÉHICULE B",
    },
    "nl": {
        "title": "EUROPEES AANRIJDINGSFORMULIER",
        "sub": "Verplicht te ondertekenen door beide bestuurders. Geen erkenning van aansprakelijkheid.",
        "date": "1. Datum van het ongeval", "time": "Uur", "place": "2. Plaats (land, gemeente, straat)",
        "injuries": "3. Gewonden, zelfs licht", "damage": "4. Materiële schade aan andere voertuigen dan A en B",
        "witnesses": "5. Getuigen: namen, adressen, tel.", "yes": "ja", "no": "neen",
        "holder": "6. Verzekeringnemer / verzekerde", "vehicle": "7. Voertuig", "insurer": "8. Verzekeringsonderneming",
        "driver": "9. Bestuurder", "impact": "10. Eerste raakpunt", "visible": "11. Zichtbare schade",
        "circ": "12. Omstandigheden", "sketch": "13. Situatieschets van het ongeval op het ogenblik van de aanrijding",
        "remarks": "14. Mijn opmerkingen", "sign": "15. Handtekening van de bestuurders",
        "name": "Naam", "first": "Voornaam", "address": "Adres", "pc": "Postcode", "country": "Land",
        "phone": "Tel. of e-mail", "make": "Merk, type", "plate": "Inschrijvingsnummer",
        "reg": "Land van inschrijving", "company": "Naam", "policy": "Polisnummer",
        "green": "Nr. groene kaart", "valid": "Geldig van / tot", "agency": "Agentschap (of kantoor, makelaar)",
        "birth": "Geboortedatum", "licence": "Rijbewijs nr.", "cat": "Categorie",
        "until": "Geldig tot", "count": "Aantal aangekruiste vakjes", "veh_a": "VOERTUIG A", "veh_b": "VOERTUIG B",
    },
}


@dataclass
class Scenario:
    key: str
    lang: str
    road: str
    circ_a: list[str]
    circ_b: list[str]
    impact_a: str
    impact_b: str
    damage_a: str
    damage_b: str
    description: str
    scanned: bool = False


SCENARIOS = [
    Scenario("rear_end", "fr", "straight_road", ["parked_or_stopped"], ["struck_rear_same_direction_same_lane"],
             "rear", "front", "pare-chocs arrière, hayon", "pare-chocs avant, capot",
             "A stopped at a red light, B hits the rear of A in the same lane."),
    Scenario("roundabout", "nl", "roundabout", ["circulating_in_roundabout"], ["entering_roundabout"],
             "right_side", "front_left", "portier rechts", "koplamp links, bumper",
             "A is driving on the roundabout, B enters it and hits the right side of A."),
    Scenario("lane_change", "fr", "multi_lane_road", ["same_direction_different_lane"], ["changing_lanes"],
             "left_side", "front_right", "aile avant gauche", "aile avant droite",
             "Both drive the same direction; B changes lanes into A."),
    Scenario("parking", "nl", "parking_lot", ["parked_or_stopped"], ["reversing"],
             "front", "rear", "bumper voor", "bumper achter",
             "A is parked, B reverses out of a parking space into the front of A.", scanned=True),
    Scenario("intersection", "fr", "intersection", ["coming_from_right_at_intersection"],
             ["ignored_priority_sign_or_red_light"],
             "front_left", "right_side", "phare avant gauche", "portière avant droite",
             "A comes from the right at an intersection; B ignored the priority sign.", scanned=True),
    Scenario("left_turn", "nl", "intersection", ["same_direction_different_lane", "overtaking"],
             ["turning_left"],
             "front_right", "left_side", "voorbumper rechts", "zijkant links",
             "B turns left while A overtakes it; A hits the left side of B."),
]

FIRST = ["Lucas", "Emma", "Noah", "Louise", "Arthur", "Olivia", "Jules", "Elise", "Victor", "Marie", "Lars", "Fien"]
LAST = ["Peeters", "Janssens", "Maes", "Dubois", "Lambert", "Wouters", "Claes", "Lemaire", "Goossens", "Martin"]
STREETS = [("Rue des Tilleuls", "1050", "Ixelles"), ("Kerkstraat", "9000", "Gent"), ("Avenue Louise", "1000", "Bruxelles"),
           ("Meir", "2000", "Antwerpen"), ("Rue de Namur", "5000", "Namur"), ("Bondgenotenlaan", "3000", "Leuven"),
           ("Chaussée de Liège", "4000", "Liège"), ("Steenweg op Brussel", "1780", "Wemmel")]
INSURERS = ["Assurances Horizon SA", "Delta Verzekeringen NV", "Mosane Assurances", "Polder Verzekeringen NV"]
CARS = ["Volkswagen Golf", "Renault Clio", "Peugeot 208", "Toyota Yaris", "BMW 318d", "Skoda Octavia", "Citroën C3", "Kia Niro"]


def plate(rng: random.Random) -> str:
    letters = "ABCDEFGHJKLMNPRSTVWXYZ"
    return f"{rng.randint(1, 2)}-{''.join(rng.choice(letters) for _ in range(3))}-{rng.randint(100, 999)}"


def vin(rng: random.Random) -> str:
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "WVW" + "".join(rng.choice(chars) for _ in range(14))


def date(rng: random.Random, y0: int, y1: int) -> str:
    return f"{rng.randint(y0, y1)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def to_be(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def person(rng: random.Random) -> dict:
    street, pc, city = rng.choice(STREETS)
    first, last = rng.choice(FIRST), rng.choice(LAST)
    return {
        "last_name": last, "first_name": first,
        "address": f"{street} {rng.randint(1, 180)}", "postal_code": pc, "city": city, "country": "BE",
        "phone": f"+32 4{rng.randint(70, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
    }


def party(rng: random.Random, circ: list[str], impact: str, damage: str) -> dict:
    holder = person(rng)
    start = date(rng, 2025, 2026)
    return {
        "policyholder": holder,
        "vehicle": {"make_model": rng.choice(CARS), "plate": plate(rng), "registration_country": "BE"},
        "insurer": {
            "company": rng.choice(INSURERS), "policy_number": f"{rng.randint(10, 99)}.{rng.randint(100000, 999999)}",
            "green_card_number": f"BE/{rng.randint(100, 999)}/{rng.randint(1000000, 9999999)}",
            "valid_from": start, "valid_to": f"{int(start[:4]) + 1}{start[4:]}",
            "agency": f"Courtier {rng.choice(LAST)} & Partners",
        },
        "driver": {
            "last_name": holder["last_name"], "first_name": holder["first_name"],
            "birth_date": date(rng, 1958, 2003), "address": None,
            "licence_number": str(rng.randint(1000000000, 9999999999)), "licence_category": "B",
            "licence_valid_until": date(rng, 2027, 2035),
        },
        "impact_point": impact,
        "visible_damage": damage,
        "remarks": None,
        "circumstances": {c: c in circ for c in CIRCUMSTANCES},
        "circumstances_count": len(circ),
    }


def accident_truth(rng: random.Random, s: Scenario) -> dict:
    street, pc, city = rng.choice(STREETS)
    witness = f"{rng.choice(FIRST)} {rng.choice(LAST)}, +32 4{rng.randint(70, 99)} {rng.randint(100000, 999999)}"
    return {
        "accident": {
            "date": date(rng, 2026, 2026), "time": f"{rng.randint(7, 20):02d}:{rng.choice(['05', '20', '35', '50'])}",
            "country": "BE", "city": city, "street": f"{street} {rng.randint(1, 120)}",
            "injuries": False, "damage_to_other_vehicles": False, "damage_to_other_objects": False,
            "witnesses": witness if rng.random() < 0.5 else None,
        },
        "vehicle_a": party(rng, s.circ_a, s.impact_a, s.damage_a),
        "vehicle_b": party(rng, s.circ_b, s.impact_b, s.damage_b),
        "sketch": {"road_layout": s.road, "description": s.description},
    }


def label(c: Canvas, x: float, y: float, text: str, size: float = 6.2) -> None:
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", size)
    c.drawString(x, y, text)


def hand(c: Canvas, x: float, y: float, text: str | None, size: float = 8.5) -> None:
    if not text:
        return
    c.setFillColor(INK)
    c.setFont(HAND, size)
    c.drawString(x, y, text)


def box(c: Canvas, x: float, y: float, w: float, h: float, fill: Color | None = None) -> None:
    c.setStrokeColor(HexColor("#777777"))
    c.setLineWidth(0.6)
    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, stroke=1, fill=1)
    else:
        c.rect(x, y, w, h, stroke=1, fill=0)


def tick(c: Canvas, x: float, y: float, s: float = 7) -> None:
    c.setStrokeColor(INK)
    c.setLineWidth(1.3)
    c.line(x + 1, y + 1, x + s - 1, y + s - 1)
    c.line(x + 1, y + s - 1, x + s - 1, y + 1)


def draw_party(c: Canvas, x: float, top: float, w: float, p: dict, L: dict, title: str, tint: Color) -> float:
    y = top
    box(c, x, y - 14, w, 14, tint)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 4, y - 10, title)
    y -= 14
    rows = [
        (L["holder"], None),
        (L["name"], p["policyholder"]["last_name"]), (L["first"], p["policyholder"]["first_name"]),
        (L["address"], p["policyholder"]["address"]),
        (L["pc"], f"{p['policyholder']['postal_code']}  {p['policyholder']['city']}  ({L['country']}: BE)"),
        (L["phone"], p["policyholder"]["phone"]),
        (L["vehicle"], None),
        (L["make"], p["vehicle"]["make_model"]), (L["plate"], p["vehicle"]["plate"]),
        (L["reg"], p["vehicle"]["registration_country"]),
        (L["insurer"], None),
        (L["company"], p["insurer"]["company"]), (L["policy"], p["insurer"]["policy_number"]),
        (L["green"], p["insurer"]["green_card_number"]),
        (L["valid"], f"{to_be(p['insurer']['valid_from'])} - {to_be(p['insurer']['valid_to'])}"),
        (L["agency"], p["insurer"]["agency"]),
        (L["driver"], None),
        (L["name"], p["driver"]["last_name"]), (L["first"], p["driver"]["first_name"]),
        (L["birth"], to_be(p["driver"]["birth_date"])),
        (L["licence"], p["driver"]["licence_number"]),
        (L["cat"], p["driver"]["licence_category"]), (L["until"], to_be(p["driver"]["licence_valid_until"])),
    ]
    for name, value in rows:
        h = 13 if value is not None else 11
        if value is None:
            box(c, x, y - h, w, h, tint)
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 6.8)
            c.drawString(x + 3, y - 8, name)
        else:
            box(c, x, y - h, w, h)
            label(c, x + 3, y - 5.5, name)
            vx = max(62, pdfmetrics.stringWidth(name, "Helvetica", 6.2) + 8)
            size = 8.0
            while size > 5 and pdfmetrics.stringWidth(value, HAND, size) > w - vx - 4:
                size -= 0.25
            hand(c, x + vx, y - 10.5, value, size)
        y -= h
    box(c, x, y - 58, w, 58)
    label(c, x + 3, y - 7, L["impact"])
    cx, cy = x + w / 2, y - 34
    c.setStrokeColor(HexColor("#555555"))
    c.roundRect(cx - 14, cy - 20, 28, 40, 6, stroke=1, fill=0)
    spots = {"front": (0, 20), "front_left": (-14, 16), "front_right": (14, 16), "left_side": (-14, 0),
             "right_side": (14, 0), "rear": (0, -20), "rear_left": (-14, -16), "rear_right": (14, -16)}
    dx, dy = spots[p["impact_point"]]
    c.setStrokeColor(INK)
    c.setLineWidth(1.6)
    c.line(cx + dx * 1.9, cy + dy * 1.5, cx + dx * 1.05, cy + dy * 1.05)
    c.circle(cx + dx * 1.05, cy + dy * 1.05, 2.5, stroke=1, fill=0)
    y -= 58
    box(c, x, y - 30, w, 30)
    label(c, x + 3, y - 7, L["visible"])
    hand(c, x + 6, y - 22, p["visible_damage"], 8.5)
    return y - 30


def draw_sketch(c: Canvas, x: float, y: float, w: float, h: float, s: Scenario) -> None:
    c.setStrokeColor(HexColor("#222222"))
    c.setLineWidth(1.1)
    mx, my = x + w / 2, y + h / 2
    if s.road == "roundabout":
        c.circle(mx, my, 34, stroke=1, fill=0)
        c.circle(mx, my, 12, stroke=1, fill=0)
        for ang in (0, 90, 180, 270):
            c.saveState(); c.translate(mx, my); c.rotate(ang)
            c.line(34, -10, 70, -10); c.line(34, 10, 70, 10); c.restoreState()
    elif s.road == "intersection":
        c.line(x + 8, my - 14, x + w - 8, my - 14); c.line(x + 8, my + 14, x + w - 8, my + 14)
        c.line(mx - 14, y + 6, mx - 14, y + h - 6); c.line(mx + 14, y + 6, mx + 14, y + h - 6)
    elif s.road == "parking_lot":
        for i in range(5):
            c.line(x + 20 + i * 30, my + 10, x + 20 + i * 30, my + 45)
        c.line(x + 10, my - 10, x + w - 10, my - 10)
    else:
        c.line(x + 8, my - 20, x + w - 8, my - 20); c.line(x + 8, my + 20, x + w - 8, my + 20)
        c.setDash(4, 4); c.line(x + 8, my, x + w - 8, my); c.setDash()
    c.setStrokeColor(INK)
    c.setFillColor(INK)
    c.setLineWidth(1.4)
    c.rect(mx - 40, my - 15, 26, 12, stroke=1, fill=0)
    c.rect(mx + 4, my - 15, 26, 12, stroke=1, fill=0)
    c.setFont(HAND, 9)
    c.drawString(mx - 31, my - 13, "A")
    c.drawString(mx + 13, my - 13, "B")
    c.line(mx + 34, my - 9, mx + 55, my - 9)
    c.line(mx - 10, my - 9, mx + 2, my - 9)


def render_accident(path: Path, t: dict, s: Scenario) -> None:
    L = LABELS[s.lang]
    c = Canvas(str(path), pagesize=A4)
    c.setTitle(f"{L['title']} - {s.key}")
    m = 22
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, H - 30, L["title"])
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(W / 2, H - 40, L["sub"])
    a = t["accident"]
    top = H - 50
    cw = (W - 2 * m) / 5
    cells = [(L["date"], to_be(a["date"])), (L["time"], a["time"]),
             (L["place"], f"BE, {a['city']}, {a['street']}")]
    box(c, m, top - 26, cw, 26); label(c, m + 3, top - 7, cells[0][0]); hand(c, m + 6, top - 21, cells[0][1])
    box(c, m + cw, top - 26, cw * 0.5, 26); label(c, m + cw + 3, top - 7, cells[1][0]); hand(c, m + cw + 6, top - 21, cells[1][1])
    box(c, m + cw * 1.5, top - 26, cw * 3.5, 26); label(c, m + cw * 1.5 + 3, top - 7, cells[2][0])
    hand(c, m + cw * 1.5 + 6, top - 21, cells[2][1])
    top -= 26
    yn = [(L["injuries"], a["injuries"]), (L["damage"], a["damage_to_other_vehicles"] or a["damage_to_other_objects"])]
    half = (W - 2 * m) / 2
    for i, (name, val) in enumerate(yn):
        bx = m + i * half
        box(c, bx, top - 20, half, 20); label(c, bx + 3, top - 8, name)
        label(c, bx + half - 70, top - 16, L["no"]); box(c, bx + half - 58, top - 17, 7, 7)
        label(c, bx + half - 40, top - 16, L["yes"]); box(c, bx + half - 28, top - 17, 7, 7)
        tick(c, bx + half - (28 if val else 58), top - 17)
    top -= 20
    box(c, m, top - 18, W - 2 * m, 18); label(c, m + 3, top - 7, L["witnesses"])
    hand(c, m + 140, top - 13, a["witnesses"] or "-")
    top -= 24
    side_w = 190
    blue, yellow = HexColor("#dbe7fb"), HexColor("#fdf3c8")
    party_bottom = draw_party(c, m, top, side_w, t["vehicle_a"], L, L["veh_a"], blue)
    draw_party(c, W - m - side_w, top, side_w, t["vehicle_b"], L, L["veh_b"], yellow)
    cx0, cx1 = m + side_w + 4, W - m - side_w - 4
    mid_w = cx1 - cx0
    box(c, cx0, top - 14, mid_w, 14)
    c.setFillColor(black); c.setFont("Helvetica-Bold", 8); c.drawCentredString(cx0 + mid_w / 2, top - 10, L["circ"])
    y = top - 14
    row_h = 19.5
    for i, key in enumerate(CIRCUMSTANCES):
        box(c, cx0, y - row_h, mid_w, row_h)
        box(c, cx0 + 4, y - row_h / 2 - 4, 8, 8); box(c, cx1 - 12, y - row_h / 2 - 4, 8, 8)
        if t["vehicle_a"]["circumstances"][key]:
            tick(c, cx0 + 4.5, y - row_h / 2 - 3.5)
        if t["vehicle_b"]["circumstances"][key]:
            tick(c, cx1 - 11.5, y - row_h / 2 - 3.5)
        c.setFillColor(HexColor("#333333")); c.setFont("Helvetica-Bold", 6); c.drawString(cx0 + 15, y - 8, str(i + 1))
        text = CIRC_LABELS[s.lang][i]
        c.setFont("Helvetica", 5.6)
        words, line, lines = text.split(), "", []
        for wd in words:
            if pdfmetrics.stringWidth(f"{line} {wd}", "Helvetica", 5.6) > mid_w - 48:
                lines.append(line); line = wd
            else:
                line = f"{line} {wd}".strip()
        lines.append(line)
        for j, ln in enumerate(lines[:2]):
            c.drawString(cx0 + 24, y - 8 - j * 6.5, ln)
        y -= row_h
    box(c, cx0, y - 16, mid_w, 16); label(c, cx0 + 24, y - 10, L["count"])
    hand(c, cx0 + 5, y - 12, str(t["vehicle_a"]["circumstances_count"]))
    hand(c, cx1 - 11, y - 12, str(t["vehicle_b"]["circumstances_count"]))
    y_sk_top = min(party_bottom, y - 16) - 6
    sk_h = y_sk_top - 90
    box(c, m, 90, W - 2 * m, sk_h)
    label(c, m + 3, y_sk_top - 8, L["sketch"])
    draw_sketch(c, m + 120, 92, W - 2 * m - 240, sk_h - 14, s)
    box(c, m, 50, side_w, 34); label(c, m + 3, 77, L["remarks"])
    box(c, W - m - side_w, 50, side_w, 34); label(c, W - m - side_w + 3, 77, L["remarks"])
    box(c, m + side_w + 4, 50, mid_w, 34); label(c, m + side_w + 7, 77, L["sign"])
    hand(c, m + side_w + 14, 58, t["vehicle_a"]["driver"]["last_name"], 11)
    hand(c, m + side_w + mid_w / 2 + 10, 58, t["vehicle_b"]["driver"]["last_name"], 11)
    c.setFont("Helvetica", 5.5); c.setFillColor(HexColor("#888888")); c.drawCentredString(W / 2, 22, SPECIMEN)
    c.showPage()
    c.save()


DEALERS = [
    {"name": "Garage Dupont Automobiles SRL", "vat": "BE0456.789.123", "city": "Namur", "lang": "fr", "style": "classic"},
    {"name": "AutoCentrum Vlaanderen NV", "vat": "BE0712.345.678", "city": "Gent", "lang": "nl", "style": "modern"},
    {"name": "Brussels Premium Motors SA", "vat": "BE0634.221.907", "city": "Bruxelles", "lang": "en", "style": "compact"},
]
MODELS = [
    ("Volkswagen", "ID.4", "Pro Performance", "electric", 150, 41990),
    ("Skoda", "Octavia Combi", "Style 1.5 TSI", "petrol", 110, 33450),
    ("Toyota", "C-HR", "Hybrid 140 Dynamic", "hybrid", 103, 36290),
    ("BMW", "X1", "sDrive18d", "diesel", 110, 46800),
    ("Renault", "Mégane E-Tech", "Techno EV60", "electric", 160, 39990),
    ("Peugeot", "3008", "Allure Hybrid 136", "hybrid", 100, 38150),
]
OPTIONS = [
    ("PAI", "Metallic paint", 790), ("WP1", "Winter pack (heated seats, steering wheel)", 650),
    ("NAV", "Navigation Pro with 12\" display", 1150), ("TOW", "Retractable tow bar", 980),
    ("PAN", "Panoramic sunroof", 1290), ("ADA", "Adaptive cruise control + lane assist", 1450),
    ("CAM", "360° parking camera", 720), ("LED", "Matrix LED headlights", 1100), ("ALU", "19\" alloy wheels", 890),
]
ORDER_LABELS = {
    "fr": {"title": "BON DE COMMANDE", "order": "N° de commande", "date": "Date", "buyer": "Acheteur",
           "vehicle": "Véhicule", "options": "Options", "price": "Prix", "base": "Prix catalogue HTVA",
           "opt": "Total options HTVA", "disc": "Remise", "net": "Net HTVA", "vat": "TVA 21%",
           "total": "Total TVAC", "fin": "Financement", "deliv": "Livraison prévue", "sales": "Conseiller"},
    "nl": {"title": "BESTELBON", "order": "Bestelnummer", "date": "Datum", "buyer": "Koper", "vehicle": "Voertuig",
           "options": "Opties", "price": "Prijs", "base": "Catalogusprijs excl. btw", "opt": "Totaal opties excl. btw",
           "disc": "Korting", "net": "Netto excl. btw", "vat": "Btw 21%", "total": "Totaal incl. btw",
           "fin": "Financiering", "deliv": "Verwachte levering", "sales": "Verkoper"},
    "en": {"title": "VEHICLE ORDER FORM", "order": "Order no.", "date": "Date", "buyer": "Buyer", "vehicle": "Vehicle",
           "options": "Options", "price": "Price", "base": "List price excl. VAT", "opt": "Options total excl. VAT",
           "disc": "Discount", "net": "Net excl. VAT", "vat": "VAT 21%", "total": "Total incl. VAT",
           "fin": "Financing", "deliv": "Expected delivery", "sales": "Sales advisor"},
}


def order_truth(rng: random.Random, dealer: dict, idx: int, broken_total: bool) -> dict:
    make, model, trim, fuel, kw, base = MODELS[idx % len(MODELS)]
    opts = rng.sample(OPTIONS, rng.randint(2, 5))
    opt_total = sum(o[2] for o in opts)
    disc = rng.choice([0, 500, 1000, 1500, 2250])
    net = base + opt_total - disc
    vat = round(net * 0.21, 2)
    total = round(net + vat, 2)
    if broken_total:
        total = round(total + 100, 2)
    company = rng.random() < 0.4
    p = person(rng)
    fin = rng.choice(["cash", "loan", "lease"])
    od = date(rng, 2026, 2026)
    return {
        "order": {"order_number": f"{dealer['name'][:2].upper()}-{rng.randint(10000, 99999)}", "order_date": od,
                  "dealer_name": dealer["name"], "dealer_vat_number": dealer["vat"],
                  "salesperson": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                  "expected_delivery": date(rng, 2026, 2027)},
        "buyer": {"type": "company" if company else "person",
                  "name": f"{p['first_name']} {p['last_name']}",
                  "company_name": f"{p['last_name']} Consult BV" if company else None,
                  "vat_number": f"BE0{rng.randint(100, 999)}.{rng.randint(100, 999)}.{rng.randint(100, 999)}" if company else None,
                  "address": p["address"], "postal_code": p["postal_code"], "city": p["city"], "phone": p["phone"],
                  "email": f"{p['first_name'].lower()}.{p['last_name'].lower()}@example.be"},
        "vehicle": {"make": make, "model": model, "trim": trim, "fuel": fuel, "power_kw": kw,
                    "color": rng.choice(["Moonstone Grey", "Deep Black", "Glacier White", "Atlantic Blue"]),
                    "vin": vin(rng) if rng.random() < 0.5 else None, "model_year": 2026},
        "options": [{"code": c, "description": d, "price_excl_vat": float(pr)} for c, d, pr in opts],
        "pricing": {"base_price_excl_vat": float(base), "options_total_excl_vat": float(opt_total),
                    "discount_excl_vat": float(disc), "net_excl_vat": float(net), "vat_rate": 21.0,
                    "vat_amount": vat, "total_incl_vat": total, "currency": "EUR"},
        "financing": {"type": fin,
                      "provider": None if fin == "cash" else rng.choice(["Belfius Auto Lease", "Alphacredit", "Beobank"]),
                      "down_payment": None if fin == "cash" else float(rng.choice([2000, 5000, 7500]))},
    }


def eur(v: float) -> str:
    return f"€ {v:,.2f}".replace(",", " ").replace(".", ",")


def render_order(path: Path, t: dict, dealer: dict) -> None:
    L = ORDER_LABELS[dealer["lang"]]
    style = dealer["style"]
    accent = {"classic": HexColor("#7a1f1f"), "modern": HexColor("#0b5d75"), "compact": HexColor("#222222")}[style]
    c = Canvas(str(path), pagesize=A4)
    c.setTitle(f"{L['title']} {t['order']['order_number']}")
    m = 40
    y = H - 50
    if style == "modern":
        c.setFillColor(accent); c.rect(0, H - 80, W, 80, stroke=0, fill=1)
        c.setFillColor(HexColor("#ffffff")); c.setFont("Helvetica-Bold", 18); c.drawString(m, H - 45, dealer["name"])
        c.setFont("Helvetica", 9); c.drawString(m, H - 62, f"{dealer['city']} · {dealer['vat']}")
        c.setFont("Helvetica-Bold", 14); c.drawRightString(W - m, H - 45, L["title"])
        y = H - 110
    else:
        c.setFillColor(accent); c.setFont("Times-Bold" if style == "classic" else "Helvetica-Bold", 16)
        c.drawString(m, y, dealer["name"])
        c.setFont("Helvetica", 8.5); c.setFillColor(black)
        c.drawString(m, y - 14, f"{dealer['city']} - TVA/BTW {dealer['vat']}")
        c.setFont("Helvetica-Bold", 13); c.drawRightString(W - m, y, L["title"])
        y -= 40
    c.setFillColor(black)

    def kv(x: float, yy: float, k: str, v: str | None, bold: bool = False) -> None:
        c.setFont("Helvetica", 8); c.setFillColor(HexColor("#555555")); c.drawString(x, yy, k)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9.5); c.setFillColor(black); c.drawString(x + 115, yy, v or "-")

    def header(yy: float, text: str) -> float:
        c.setFillColor(accent); c.setFont("Helvetica-Bold", 10.5); c.drawString(m, yy, text.upper())
        c.setStrokeColor(accent); c.setLineWidth(0.8); c.line(m, yy - 4, W - m, yy - 4)
        return yy - 20

    o, b, v = t["order"], t["buyer"], t["vehicle"]
    kv(m, y, L["order"], o["order_number"], True); kv(W / 2, y, L["date"], to_be(o["order_date"])); y -= 14
    kv(m, y, L["sales"], o["salesperson"]); kv(W / 2, y, L["deliv"], to_be(o["expected_delivery"])); y -= 26
    y = header(y, L["buyer"])
    kv(m, y, "Name / Nom / Naam", b["name"]); kv(W / 2, y, "Company", b["company_name"]); y -= 14
    kv(m, y, "Address", f"{b['address']}, {b['postal_code']} {b['city']}"); y -= 14
    kv(m, y, "VAT", b["vat_number"]); kv(W / 2, y, "Tel.", b["phone"]); y -= 14
    kv(m, y, "E-mail", b["email"]); y -= 26
    y = header(y, L["vehicle"])
    kv(m, y, "Make / Marque / Merk", v["make"]); kv(W / 2, y, "Model", v["model"]); y -= 14
    kv(m, y, "Version", v["trim"]); kv(W / 2, y, "Fuel", v["fuel"]); y -= 14
    kv(m, y, "Power (kW)", str(v["power_kw"])); kv(W / 2, y, "Colour", v["color"]); y -= 14
    kv(m, y, "VIN", v["vin"]); kv(W / 2, y, "Model year", str(v["model_year"])); y -= 26
    y = header(y, L["options"])
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(m, y, "Code"); c.drawString(m + 60, y, "Description"); c.drawRightString(W - m, y, "HTVA / excl.")
    y -= 13
    c.setFont("Helvetica", 9)
    for opt in t["options"]:
        c.drawString(m, y, opt["code"]); c.drawString(m + 60, y, opt["description"])
        c.drawRightString(W - m, y, eur(opt["price_excl_vat"])); y -= 13
    y -= 14
    y = header(y, L["price"])
    pr = t["pricing"]
    for k, val in [(L["base"], pr["base_price_excl_vat"]), (L["opt"], pr["options_total_excl_vat"]),
                   (L["disc"], -pr["discount_excl_vat"]), (L["net"], pr["net_excl_vat"]), (L["vat"], pr["vat_amount"])]:
        c.setFont("Helvetica", 9.5); c.drawString(W / 2, y, k); c.drawRightString(W - m, y, eur(val)); y -= 14
    c.setFont("Helvetica-Bold", 11); c.drawString(W / 2, y - 2, L["total"]); c.drawRightString(W - m, y - 2, eur(pr["total_incl_vat"]))
    y -= 34
    y = header(y, L["fin"])
    f = t["financing"]
    kv(m, y, "Type", f["type"]); kv(W / 2, y, "Provider", f["provider"]); y -= 14
    kv(m, y, "Down payment", eur(f["down_payment"]) if f["down_payment"] is not None else None); y -= 40
    c.setFont("Helvetica", 8); c.setFillColor(HexColor("#555555"))
    c.drawString(m, y, "Signature acheteur / koper / buyer"); c.drawString(W / 2, y, "Signature vendeur / verkoper / dealer")
    c.setFont(HAND, 13); c.setFillColor(INK); c.drawString(m + 10, y - 26, b["name"].split()[-1])
    c.setFont("Helvetica", 5.5); c.setFillColor(HexColor("#888888")); c.drawCentredString(W / 2, 22, SPECIMEN)
    c.showPage()
    c.save()


def scan(path: Path, seed: int) -> None:
    """Re-render a PDF as a slightly rotated, noisy greyscale scan."""
    rng = random.Random(seed)
    doc = fitz.open(path)
    out = fitz.open()
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        img = img.rotate(rng.uniform(-1.4, 1.4), expand=False, fillcolor=245, resample=Image.BICUBIC)
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        noise = Image.effect_noise(img.size, 18).convert("L")
        img = Image.blend(img, noise, 0.08)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55)
        rect = page.rect
        new = out.new_page(width=rect.width, height=rect.height)
        new.insert_image(rect, stream=buf.getvalue())
    doc.close()
    out.save(path)


def main() -> None:
    rng = random.Random(42)
    (SAMPLES / "accident_statements").mkdir(parents=True, exist_ok=True)
    (SAMPLES / "order_forms").mkdir(parents=True, exist_ok=True)
    (TRUTH / "accident_statements").mkdir(parents=True, exist_ok=True)
    (TRUTH / "order_forms").mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(SCENARIOS, start=1):
        name = f"accident_{i:02d}_{s.key}_{s.lang}{'_scan' if s.scanned else ''}"
        truth = accident_truth(rng, s)
        pdf = SAMPLES / "accident_statements" / f"{name}.pdf"
        render_accident(pdf, truth, s)
        if s.scanned:
            scan(pdf, i)
        (TRUTH / "accident_statements" / f"{name}.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
    for i in range(6):
        dealer = DEALERS[i % len(DEALERS)]
        broken = i == 4
        name = f"order_{i + 1:02d}_{dealer['style']}_{dealer['lang']}{'_bad_total' if broken else ''}{'_scan' if i == 5 else ''}"
        truth = order_truth(rng, dealer, i, broken)
        pdf = SAMPLES / "order_forms" / f"{name}.pdf"
        render_order(pdf, truth, dealer)
        if i == 5:
            scan(pdf, 100 + i)
        (TRUTH / "order_forms" / f"{name}.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote samples to {SAMPLES} and ground truth to {TRUTH}")


if __name__ == "__main__":
    main()
