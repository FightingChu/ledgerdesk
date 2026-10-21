"""Create clearly synthetic standard CSV inputs exclusively in a new directory."""
import argparse
import csv
from pathlib import Path


def generate(destination, groups):
    if type(groups) is not int or not 1 <= groups <= 10000:
        raise ValueError("Each synthetic file supports 1..10000 groups")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for side in ("orders", "payments"):
        with (destination / (side + ".csv")).open("x", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["order_id", "amount", "channel"] if side == "orders" else ["order_id", "transaction_id", "amount", "event_type", "channel"])
            for index in range(groups):
                key, channel = f"SYN{index:08}", "synthetic_" + str(index % 5)
                writer.writerow([key, "1.01", channel] if side == "orders" else [key, "SYN-P" + str(index), "1.00", "sale", channel])
    (destination / "README.txt").write_text("Synthetic standard CSV test data.\n", encoding="utf-8")
    return {"groups": groups, "files": 2, "synthetic": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path); parser.add_argument("--groups", type=int, default=1000)
    args = parser.parse_args()
    print(generate(args.destination, args.groups))
