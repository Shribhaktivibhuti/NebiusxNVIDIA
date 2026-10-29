# Prompt given to the chatbot: "Write a Python function that reads a CSV of orders
# (columns: order_id, amount) and returns the average order value."
# Typical AI-style bugs planted for testing Vibe Bro:
#   1. counts the header row as an order
#   2. crashes on an empty file (division by zero)
#   3. imports a package that does not exist on PyPI


def average_order_value(path):
    total = 0.0
    count = 0
    with open(path) as f:
        for line in f:
            parts = line.strip().split(",")
            try:
                total += float(parts[1])
            except ValueError:
                pass
            count += 1
    return total / count


if __name__ == "__main__":
    import csv_utils_pro  # noqa: F401  (invented package)
    print(average_order_value("orders.csv"))
