-- Sample schema for QueryAI demo

DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS orders;

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    country TEXT
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    product TEXT NOT NULL,
    amount REAL NOT NULL,
    order_date TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

INSERT INTO users (id, name, email, country) VALUES
    (1, 'Alice', 'alice@example.com', 'USA'),
    (2, 'Bob', 'bob@example.com', 'Canada'),
    (3, 'Charlie', 'charlie@example.com', 'UK');

INSERT INTO orders (id, user_id, product, amount, order_date) VALUES
    (1, 1, 'Laptop', 1200.00, '2024-01-05'),
    (2, 1, 'Mouse', 25.50, '2024-01-10'),
    (3, 2, 'Keyboard', 75.00, '2024-02-02'),
    (4, 3, 'Monitor', 300.00, '2024-02-15');
