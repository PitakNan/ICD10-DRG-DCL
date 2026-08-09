"""ICD-10 → DC pairs where the DRG group depends on patient age, not the code alone.

TDS6307's sweep in runner.py fixes Age=70 for every code, so any PDC whose DC
branches on age only ever recorded one side. Confirmed empirically by firing
one representative code per affected PDC through the live grouper at age=5
and age=70 (scripts/age_probe.py, run 2026-08-09) and reading the DC each
side actually resolves to -- see age_probe.csv for the raw transcript.
"""

# pdc -> (cutoff_age, dc_if_age_below_cutoff, dc_if_age_at_or_above_cutoff)
AGE_SPLIT = {
    '11A': (18, '1151', '1150'),  # Chronic renal failure
    '11J': (18, '1160', '1159'),  # Acute renal failure
    '2A':  (55, '0252', '0251'),  # Acute and major eye infections
    '21A': (18, '2151', '2150'),  # Traumatic injury
    '21B': (18, '2153', '2152'),  # Allergic reactions
    '21C': (18, '2155', '2154'),  # Poisoning & toxic effects of drugs
    '8P':  (18, '0864', '0863'),  # Fx/spr/str/disl of forearm, hand & foot
    '8Q':  (18, '0866', '0865'),  # Fx/spr/str/disl of upper arm & lower leg
    '9G':  (18, '0957', '0956'),  # Cellulitis
    '9H':  (18, '0959', '0958'),  # Trauma to skin, subcut tissue & breast
    '6G':  (10, '0658', '0657'),  # Gastroenteritis (infectious)
    '6N':  (10, '0658', '0676'),  # Gastroenteritis / non-infectious gastroenteritis
    '6H':  (10, '0663', '0666'),  # Intestinal helminth & misc digestive dis
    '6L':  (10, '0663', '0662'),  # Intestinal helminthiases
    '6M':  (10, '0665', '0664'),  # Oesophagitis, gastritis and dyspepsia
}
