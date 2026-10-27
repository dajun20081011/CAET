"""Explicit operator CLI for creating/updating a user without shipping seed accounts."""

import argparse
import getpass

from .config import settings
from .security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", choices=["learner", "evaluator", "instructor", "admin"], required=True)
    parser.add_argument("--email")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    password = input().rstrip("\n") if args.password_stdin else getpass.getpass("Password: ")
    password_hash = hash_password(password)

    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required")
    import psycopg
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users(external_ref,display_name,email,password_hash)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT(external_ref) DO UPDATE SET
                 display_name=excluded.display_name,email=excluded.email,password_hash=excluded.password_hash,
                 token_version=users.token_version+1,is_active=true
               RETURNING id""",
            (args.account, args.display_name, args.email, password_hash),
        )
        user_id = cur.fetchone()[0]
        cur.execute("SELECT id FROM products WHERE code='cabinlingo'")
        product = cur.fetchone()
        if not product:
            raise SystemExit("Run 0004_cabinlingo_rbac_catalog.sql first")
        product_id = product[0]
        cur.execute(
            """INSERT INTO product_memberships(user_id,product_id,status) VALUES (%s,%s,'active')
               ON CONFLICT(user_id,product_id) DO UPDATE SET status='active'""",
            (user_id, product_id),
        )
        cur.execute("SELECT id FROM roles WHERE product_id=%s AND code=%s", (product_id, args.role))
        role = cur.fetchone()
        if not role:
            raise SystemExit("Role catalog is missing")
        cur.execute("INSERT INTO user_roles(user_id,role_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user_id, role[0]))
    print(f"USER_PROVISIONED={args.account}")


if __name__ == "__main__":
    main()
