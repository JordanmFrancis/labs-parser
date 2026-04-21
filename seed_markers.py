from db import init_db, get_conn
from models import MarkerDef

SEED = [
    MarkerDef(name="Total Cholesterol", short_name="Total Chol", unit="mg/dL", range_low=0, range_high=200, optimal_low=140, optimal_high=180, group_name="lipids"),
    MarkerDef(name="LDL-C", short_name="LDL", unit="mg/dL", range_low=0, range_high=100, optimal_low=70, optimal_high=100, group_name="lipids"),
    MarkerDef(name="HDL", short_name="HDL", unit="mg/dL", range_low=45, range_high=100, optimal_low=55, optimal_high=80, group_name="lipids"),
    MarkerDef(name="Triglycerides", short_name="TG", unit="mg/dL", range_low=0, range_high=150, optimal_low=40, optimal_high=100, group_name="lipids"),
    MarkerDef(name="Lp(a)", short_name="Lp(a)", unit="nmol/L", range_low=0, range_high=75, optimal_low=0, optimal_high=30, group_name="lipids"),
    MarkerDef(name="ApoB", short_name="ApoB", unit="mg/dL", range_low=0, range_high=90, optimal_low=0, optimal_high=70, group_name="lipids"),
    MarkerDef(name="HbA1c", short_name="HbA1c", unit="%", range_low=0, range_high=5.7, optimal_low=4.6, optimal_high=5.3, group_name="metabolic"),
    MarkerDef(name="Glucose", short_name="Glucose", unit="mg/dL", range_low=65, range_high=99, optimal_low=75, optimal_high=90, group_name="metabolic"),
    MarkerDef(name="Insulin", short_name="Insulin", unit="uIU/mL", range_low=0, range_high=18.4, optimal_low=2, optimal_high=7, group_name="metabolic"),
    MarkerDef(name="hs-CRP", short_name="hs-CRP", unit="mg/L", range_low=0, range_high=1.0, optimal_low=0, optimal_high=0.5, group_name="inflammation"),
    MarkerDef(name="Homocysteine", short_name="Homocys", unit="umol/L", range_low=0, range_high=12.9, optimal_low=5, optimal_high=8, group_name="inflammation"),
    MarkerDef(name="Globulin", short_name="Globulin", unit="g/dL", range_low=2.1, range_high=3.5, optimal_low=2.4, optimal_high=2.8, group_name="proteins"),
    MarkerDef(name="TSH", short_name="TSH", unit="mIU/L", range_low=0.4, range_high=4.5, optimal_low=1.0, optimal_high=2.0, group_name="thyroid"),
    MarkerDef(name="Free T4", short_name="Free T4", unit="ng/dL", range_low=0.8, range_high=1.8, optimal_low=1.0, optimal_high=1.4, group_name="thyroid"),
    MarkerDef(name="Creatinine", short_name="Creat", unit="mg/dL", range_low=0.6, range_high=1.2, optimal_low=0.7, optimal_high=1.0, group_name="kidney"),
    MarkerDef(name="eGFR", short_name="eGFR", unit="mL/min", range_low=60, range_high=120, optimal_low=90, optimal_high=120, group_name="kidney"),
    MarkerDef(name="ALT", short_name="ALT", unit="U/L", range_low=7, range_high=52, optimal_low=10, optimal_high=25, group_name="liver"),
    MarkerDef(name="AST", short_name="AST", unit="U/L", range_low=13, range_high=39, optimal_low=15, optimal_high=25, group_name="liver"),
]


def seed():
    init_db()
    with get_conn() as conn:
        count = 0
        for marker in SEED:
            conn.execute(
                "INSERT OR IGNORE INTO markers (name, short_name, unit, range_low, range_high, optimal_low, optimal_high, group_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (marker.name, marker.short_name, marker.unit, marker.range_low, marker.range_high, marker.optimal_low, marker.optimal_high, marker.group_name)
            )
            count += 1
        print(f"Seeded {count} markers.")


if __name__ == "__main__":
    seed()