import sys
from sqlalchemy import text
from backend.db.session import engine

statements = [
    # 1. Drop foreign key constraints on product_id
    "ALTER TABLE daily_product_demand DROP CONSTRAINT IF EXISTS daily_product_demand_product_id_fkey;",
    "ALTER TABLE inventory DROP CONSTRAINT IF EXISTS inventory_product_id_fkey;",
    "ALTER TABLE inventory_recommendations DROP CONSTRAINT IF EXISTS inventory_recommendations_product_id_fkey;",
    "ALTER TABLE anomalies DROP CONSTRAINT IF EXISTS anomalies_product_id_fkey;",
    "ALTER TABLE sales DROP CONSTRAINT IF EXISTS sales_product_id_fkey;",
    "ALTER TABLE forecasts DROP CONSTRAINT IF EXISTS forecasts_product_id_fkey;",
    "ALTER TABLE forecast_evaluations DROP CONSTRAINT IF EXISTS forecast_evaluations_product_id_fkey;",

    # 2. Alter column types to VARCHAR(100)
    "ALTER TABLE products ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE sales ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE daily_product_demand ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE inventory ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE inventory_recommendations ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE anomalies ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE forecasts ALTER COLUMN product_id TYPE VARCHAR(100);",
    "ALTER TABLE forecast_evaluations ALTER COLUMN product_id TYPE VARCHAR(100);",

    # 3. Re-add foreign key constraints with ON DELETE CASCADE
    "ALTER TABLE daily_product_demand ADD CONSTRAINT daily_product_demand_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE inventory ADD CONSTRAINT inventory_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE inventory_recommendations ADD CONSTRAINT inventory_recommendations_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE anomalies ADD CONSTRAINT anomalies_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE sales ADD CONSTRAINT sales_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE forecasts ADD CONSTRAINT forecasts_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
    "ALTER TABLE forecast_evaluations ADD CONSTRAINT forecast_evaluations_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE;",
]

def run_migration():
    print(f"Connecting to database: {engine.url.render_as_string(hide_password=True)}")
    with engine.connect() as conn:
        for stmt in statements:
            print(f"Running: {stmt}")
            conn.execute(text(stmt))
        conn.commit()
    print("Migration to VARCHAR(100) completed successfully!")

if __name__ == "__main__":
    run_migration()
