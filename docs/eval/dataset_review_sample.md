# Dataset Review Sample

Hand-pick 15 dev-split cases for spot-checking.

## ec-001  (ecommerce | easy | aggregation)

**Question:** How many customers are registered?

**Gold SQL:**
`sql
SELECT count(*) AS customer_count FROM public.customers
`

**Expected intent:** ANSWER

## ec-002  (ecommerce | easy | aggregation)

**Question:** What is the total number of orders placed?

**Gold SQL:**
`sql
SELECT count(*) AS order_count FROM public.orders
`

**Expected intent:** ANSWER

## ec-004  (ecommerce | easy | aggregation)

**Question:** What is the average order value?

**Gold SQL:**
`sql
SELECT avg(total_amount) AS avg_order_value FROM public.orders
`

**Expected intent:** ANSWER

## ec-005  (ecommerce | easy | aggregation)

**Question:** How many products are in the catalog?

**Gold SQL:**
`sql
SELECT count(*) AS product_count FROM public.products
`

**Expected intent:** ANSWER

## ec-006  (ecommerce | easy | filter)

**Question:** Which customers are from New York?

**Gold SQL:**
`sql
SELECT customer_id, name, email FROM public.customers WHERE city = 'New York'
`

**Expected intent:** ANSWER

## ec-007  (ecommerce | easy | filter)

**Question:** Show orders with a total amount greater than 500.

**Gold SQL:**
`sql
SELECT order_id, customer_id, total_amount FROM public.orders WHERE total_amount > 500 ORDER BY total_amount DESC
`

**Expected intent:** ANSWER

## ec-008  (ecommerce | easy | filter)

**Question:** Which products have a stock quantity below 10?

**Gold SQL:**
`sql
SELECT product_id, name, stock_quantity FROM public.products WHERE stock_quantity < 10 ORDER BY stock_quantity
`

**Expected intent:** ANSWER

## ec-009  (ecommerce | easy | filter)

**Question:** List all orders with status 'cancelled'.

**Gold SQL:**
`sql
SELECT order_id, customer_id, total_amount, created_at FROM public.orders WHERE status = 'cancelled'
`

**Expected intent:** ANSWER

## ec-011  (ecommerce | medium | join)

**Question:** Show all order items with the product name and quantity ordered.

**Gold SQL:**
`sql
SELECT oi.order_item_id, p.name AS product_name, oi.quantity, oi.unit_price
FROM public.order_items oi
JOIN public.products p ON p.product_id = oi.product_id
ORDER BY oi.order_item_id
`

**Expected intent:** ANSWER

## ec-012  (ecommerce | medium | join)

**Question:** Which customers have placed more than 3 orders?

**Gold SQL:**
`sql
SELECT c.customer_id, c.name, count(o.order_id) AS order_count
FROM public.customers c
JOIN public.orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name
HAVING count(o.order_id) > 3
ORDER BY order_count DESC
`

**Expected intent:** ANSWER

## ec-013  (ecommerce | medium | grouping)

**Question:** What is the total revenue per product category?

**Gold SQL:**
`sql
SELECT p.category, sum(oi.quantity * oi.unit_price) AS revenue
FROM public.order_items oi
JOIN public.products p ON p.product_id = oi.product_id
GROUP BY p.category
ORDER BY revenue DESC
`

**Expected intent:** ANSWER

## ec-014  (ecommerce | medium | grouping)

**Question:** How many orders were placed each month this year?

**Gold SQL:**
`sql
SELECT date_trunc('month', created_at) AS month, count(*) AS order_count
FROM public.orders
WHERE date_part('year', created_at) = date_part('year', CURRENT_DATE)
GROUP BY 1
ORDER BY 1
`

**Expected intent:** ANSWER

## ec-015  (ecommerce | medium | grouping)

**Question:** What is the average order value per customer city?

**Gold SQL:**
`sql
SELECT c.city, avg(o.total_amount) AS avg_order_value
FROM public.orders o
JOIN public.customers c ON c.customer_id = o.customer_id
GROUP BY c.city
ORDER BY avg_order_value DESC
`

**Expected intent:** ANSWER

## ec-016  (ecommerce | medium | time)

**Question:** How many orders were placed in the last 30 days?

**Gold SQL:**
`sql
SELECT count(*) AS recent_order_count
FROM public.orders
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
`

**Expected intent:** ANSWER

## ec-017  (ecommerce | medium | time)

**Question:** What was the total revenue last month?

**Gold SQL:**
`sql
SELECT sum(total_amount) AS last_month_revenue
FROM public.orders
WHERE date_trunc('month', created_at) = date_trunc('month', CURRENT_DATE - INTERVAL '1 month')
`

**Expected intent:** ANSWER
