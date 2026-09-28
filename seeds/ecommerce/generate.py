import argparse
import datetime
import random
from pathlib import Path

SEED = 42
# The committed demo data is intentionally reproducible. Refresh this date when
# refreshing the fixture so its dates remain recent without changing the output
# between two generator runs.
REFERENCE_DATE = datetime.datetime(2026, 9, 28, 12, 0, 0)

def generate_ecommerce(output_dir: Path | None = None) -> None:
    """Generate the deterministic ecommerce schema and fixture data."""
    rng = random.Random(SEED)
    base_dir = output_dir or Path(__file__).resolve().parent
    base_dir.mkdir(parents=True, exist_ok=True)
    schema_path = base_dir / "01_schema.sql"
    data_path = base_dir / "02_data.sql"

    schema = """
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    category_id INTEGER REFERENCES categories(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    status VARCHAR(50) NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    order_date TIMESTAMP WITH TIME ZONE NOT NULL,
    shipped_date TIMESTAMP WITH TIME ZONE
);

CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL
);
"""
    with schema_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(schema.strip() + "\n")

    # Generate Data
    categories = [
        "Electronics", "Clothing", "Books", "Home & Garden", "Sports"
    ]
    
    first_names = ["John", "Jane", "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"]
    last_names = ["Smith", "Doe", "Johnson", "Brown", "Taylor", "Anderson", "Thomas", "Jackson"]
    statuses = ["pending", "shipped", "delivered", "cancelled"]

    data_lines = []

    # Categories
    data_lines.append("INSERT INTO categories (name, description) VALUES")
    cat_values = []
    for c in categories:
        cat_values.append(f"('{c}', '{c} description')")
    data_lines.append(",\n".join(cat_values) + ";\n")

    # Products (20 products)
    data_lines.append("INSERT INTO products (category_id, name, price, stock_quantity) VALUES")
    prod_values = []
    for i in range(1, 21):
        cat_id = rng.randint(1, len(categories))
        price = round(rng.uniform(10.0, 500.0), 2)
        stock = rng.randint(0, 100)
        prod_values.append(f"({cat_id}, 'Product {i}', {price}, {stock})")
    data_lines.append(",\n".join(prod_values) + ";\n")

    # Customers (50 customers)
    data_lines.append("INSERT INTO customers (first_name, last_name, email, phone, is_active, created_at) VALUES")
    cust_values = []
    today = REFERENCE_DATE
    for i in range(1, 51):
        fn = rng.choice(first_names)
        ln = rng.choice(last_names)
        email = f"{fn.lower()}.{ln.lower()}{i}@example.com"
        phone = f"555-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}" if rng.random() > 0.2 else "NULL"
        active = "TRUE" if rng.random() > 0.1 else "FALSE"
        days_ago = rng.randint(1, 1000)
        created_at = today - datetime.timedelta(days=days_ago)
        
        # Phone string needs quotes if not NULL
        phone_val = f"'{phone}'" if phone != "NULL" else "NULL"
        cust_values.append(f"('{fn}', '{ln}', '{email}', {phone_val}, {active}, '{created_at.strftime('%Y-%m-%d %H:%M:%S')}')")
    data_lines.append(",\n".join(cust_values) + ";\n")

    # Orders & Items
    orders_values = []
    items_values = []
    order_id = 1
    
    for _ in range(200): # 200 orders
        cust_id = rng.randint(1, 50)
        status = rng.choices(statuses, weights=[10, 20, 60, 10])[0]
        
        days_ago = rng.randint(1, 1000)
        order_date = today - datetime.timedelta(days=days_ago)
        
        shipped_date = "NULL"
        if status in ["shipped", "delivered"]:
            shipped = order_date + datetime.timedelta(days=rng.randint(1, 7))
            shipped_date = f"'{shipped.strftime('%Y-%m-%d %H:%M:%S')}'"
            
        # We will update total_amount after items
        total_amount = 0
        
        num_items = rng.randint(1, 5)
        for _ in range(num_items):
            prod_id = rng.randint(1, 20)
            qty = rng.randint(1, 3)
            # Fetch price from deterministic products but for simplicity we'll just random it here as well
            unit_price = round(rng.uniform(10.0, 500.0), 2)
            total_amount += qty * unit_price
            items_values.append(f"({order_id}, {prod_id}, {qty}, {unit_price})")
            
        total_amount = round(total_amount, 2)
        orders_values.append(f"({cust_id}, '{status}', {total_amount}, '{order_date.strftime('%Y-%m-%d %H:%M:%S')}', {shipped_date})")
        
        order_id += 1

    data_lines.append("INSERT INTO orders (customer_id, status, total_amount, order_date, shipped_date) VALUES")
    data_lines.append(",\n".join(orders_values) + ";\n")

    data_lines.append("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES")
    data_lines.append(",\n".join(items_values) + ";\n")

    with data_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(data_lines))

    print(f"Generated {schema_path} and {data_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate deterministic ecommerce demo data.")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    generate_ecommerce(args.output_dir)
