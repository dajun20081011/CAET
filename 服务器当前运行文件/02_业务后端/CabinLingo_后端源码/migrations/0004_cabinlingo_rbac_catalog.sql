-- Product/role/permission metadata only. No users, passwords or demo content.
INSERT INTO products(code,name,status) VALUES ('cabinlingo','CabinLingo','implemented')
ON CONFLICT(code) DO UPDATE SET name=excluded.name,status=excluded.status;

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO permissions(product_id,code,name)
SELECT product.id,item.code,item.name FROM product CROSS JOIN (VALUES
  ('cabinlingo:read','Read CabinLingo content'),
  ('cabinlingo:learn','Submit own practice and exam work'),
  ('cabinlingo:task.manage','Create and assign tasks'),
  ('cabinlingo:review','Review exam submissions'),
  ('cabinlingo:admin','Administer CabinLingo')
) AS item(code,name)
ON CONFLICT(product_id,code) DO UPDATE SET name=excluded.name;

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO roles(product_id,code,name)
SELECT product.id,item.code,item.name FROM product CROSS JOIN (VALUES
  ('learner','Learner'),('evaluator','Evaluator'),('instructor','Instructor'),('admin','Administrator')
) AS item(code,name)
ON CONFLICT(product_id,code) DO UPDATE SET name=excluded.name;

INSERT INTO role_permissions(role_id,permission_id)
SELECT role.id,permission.id
FROM roles role
JOIN products product ON product.id=role.product_id AND product.code='cabinlingo'
JOIN permissions permission ON permission.product_id=product.id
WHERE
  (role.code='learner' AND permission.code IN ('cabinlingo:read','cabinlingo:learn')) OR
  (role.code='evaluator' AND permission.code IN ('cabinlingo:read','cabinlingo:review')) OR
  (role.code='instructor' AND permission.code IN ('cabinlingo:read','cabinlingo:task.manage','cabinlingo:review')) OR
  (role.code='admin')
ON CONFLICT DO NOTHING;
