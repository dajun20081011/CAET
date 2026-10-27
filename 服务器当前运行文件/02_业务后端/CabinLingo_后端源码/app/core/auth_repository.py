from __future__ import annotations

from typing import Any


class AuthRepository:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def find_user_for_login(self, account: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id::text AS id,external_ref,display_name,email,password_hash,token_version,is_active
                   FROM users WHERE lower(external_ref)=lower(%s) OR lower(email)=lower(%s) LIMIT 1""",
                (account, account),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def touch_login(self, user_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE users SET last_login_at=now() WHERE id=%s", (user_id,))

    def get_identity(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id::text AS id,display_name,email,token_version,is_active FROM users WHERE id=%s",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                return None
            cur.execute(
                """SELECT p.code AS product_code,r.code AS role_code,permission.code AS permission_code
                   FROM product_memberships membership
                   JOIN products p ON p.id=membership.product_id
                   LEFT JOIN user_roles ur ON ur.user_id=membership.user_id
                   LEFT JOIN roles r ON r.id=ur.role_id AND r.product_id=p.id
                   LEFT JOIN role_permissions rp ON rp.role_id=r.id
                   LEFT JOIN permissions permission ON permission.id=rp.permission_id
                   WHERE membership.user_id=%s AND membership.status='active'
                   ORDER BY p.code,r.code,permission.code""",
                (user_id,),
            )
            memberships: dict[str, dict[str, set[str]]] = {}
            for row in cur.fetchall():
                item = memberships.setdefault(row["product_code"], {"roles": set(), "permissions": set()})
                if row["role_code"]:
                    item["roles"].add(row["role_code"])
                if row["permission_code"]:
                    item["permissions"].add(row["permission_code"])
            result = dict(user)
            result["memberships"] = memberships
            return result

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT u.id::text AS id,u.external_ref,u.display_name,u.email,u.is_active,
                          COALESCE(u.class_id::text, MAX(membership.class_id::text)) AS class_id,
                          COALESCE(array_agg(DISTINCT r.code) FILTER (WHERE r.code IS NOT NULL), ARRAY[]::text[]) AS roles
                          FROM users u LEFT JOIN product_memberships membership ON membership.user_id=u.id
                          LEFT JOIN user_roles ur ON ur.user_id=u.id LEFT JOIN roles r ON r.id=ur.role_id
                          GROUP BY u.id ORDER BY u.created_at DESC""")
            return [dict(row) for row in cur.fetchall()]

    def create_user(self, account: str, display_name: str, email: str | None, password_hash: str, role: str, class_id: str | None, actor_id: str | None = None) -> dict[str, Any]:
        if role not in {"learner", "evaluator", "instructor", "admin"}:
            raise ValueError("unsupported user role")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO users(external_ref,display_name,email,password_hash,password_updated_at,class_id)
                          VALUES (%s,%s,%s,%s,now(),%s) RETURNING id::text AS id,external_ref,display_name,email,is_active,class_id""", (account, display_name, email, password_hash, class_id))
            user = dict(cur.fetchone())
            cur.execute("SELECT id FROM products WHERE code='cabinlingo'")
            product = cur.fetchone()
            if not product:
                raise ValueError("CabinLingo product catalog is missing")
            cur.execute("INSERT INTO product_memberships(user_id,product_id,class_id,status) VALUES (%s,%s,%s,'active') ON CONFLICT(user_id,product_id) DO UPDATE SET class_id=EXCLUDED.class_id,status='active'", (user["id"], product["id"], class_id))
            if class_id:
                cur.execute("""INSERT INTO class_memberships(class_id,user_id,status) VALUES (%s,%s,'active')
                               ON CONFLICT(class_id,user_id) DO UPDATE SET status='active'""", (class_id, user["id"]))
            cur.execute("SELECT id FROM roles WHERE product_id=%s AND code=%s", (product["id"], role))
            role_row = cur.fetchone()
            if role_row:
                cur.execute("INSERT INTO user_roles(user_id,role_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (user["id"], role_row["id"]))
            if actor_id:
                cur.execute("""INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                               VALUES (%s,'cabinlingo','user.created','user',%s,'{}'::jsonb)""", (actor_id, user["id"]))
            user["roles"] = [role]
            return user

    def update_imported_user(
        self, account: str, display_name: str, password_hash: str, actor_id: str,
        *, email: str | None, role: str, class_id: str | None,
    ) -> dict[str, Any] | None:
        """Repair an existing imported user without replacing identity or history."""
        if role not in {"learner", "evaluator", "instructor", "admin"}:
            raise ValueError("unsupported user role")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id::text AS id,is_active FROM users WHERE lower(external_ref)=lower(%s) LIMIT 1",
                (account,),
            )
            existing = cur.fetchone()
            if not existing:
                return None
            cur.execute(
                """UPDATE users
                   SET display_name=%s,email=COALESCE(%s,email),class_id=COALESCE(%s,class_id),
                       password_hash=%s,password_updated_at=now(),
                       token_version=token_version+1,is_active=true,deactivated_reason=NULL
                   WHERE id=%s""",
                (display_name, email, class_id, password_hash, existing["id"]),
            )
            cur.execute("SELECT id FROM products WHERE code='cabinlingo'")
            product = cur.fetchone()
            if not product:
                raise ValueError("CabinLingo product catalog is missing")
            cur.execute(
                """INSERT INTO product_memberships(user_id,product_id,class_id,status)
                   VALUES (%s,%s,%s,'active') ON CONFLICT(user_id,product_id)
                   DO UPDATE SET class_id=COALESCE(EXCLUDED.class_id,product_memberships.class_id),status='active'""",
                (existing["id"], product["id"], class_id),
            )
            if class_id:
                cur.execute(
                    """INSERT INTO class_memberships(class_id,user_id,status) VALUES (%s,%s,'active')
                       ON CONFLICT(class_id,user_id) DO UPDATE SET status='active'""",
                    (class_id, existing["id"]),
                )
            cur.execute("SELECT id FROM roles WHERE product_id=%s AND code=%s", (product["id"], role))
            role_row = cur.fetchone()
            if not role_row:
                raise ValueError("unsupported user role")
            cur.execute(
                "INSERT INTO user_roles(user_id,role_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (existing["id"], role_row["id"]),
            )
            action = "user.import_name_updated" if existing["is_active"] else "user.import_reactivated"
            cur.execute(
                """INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                   VALUES (%s,'cabinlingo',%s,'user',%s,'{}'::jsonb)""",
                (actor_id, action, existing["id"]),
            )
            return self._get_user_for_cursor(cur, existing["id"])

    def _get_user_for_cursor(self, cur, user_id: str) -> dict[str, Any] | None:
        cur.execute("""SELECT u.id::text AS id,u.external_ref,u.display_name,u.email,u.is_active,
                      COALESCE(u.class_id::text, MAX(membership.class_id::text)) AS class_id,
                      COALESCE(array_agg(DISTINCT r.code) FILTER (WHERE r.code IS NOT NULL), ARRAY[]::text[]) AS roles
                      FROM users u LEFT JOIN product_memberships membership ON membership.user_id=u.id
                      LEFT JOIN user_roles ur ON ur.user_id=u.id LEFT JOIN roles r ON r.id=ur.role_id
                      WHERE u.id=%s GROUP BY u.id""", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def deactivate_user(self, user_id: str, actor_id: str) -> dict[str, Any]:
        if user_id == actor_id:
            raise ValueError("cannot deactivate the current user")
        with self._connect() as conn, conn.cursor() as cur:
            user = self._get_user_for_cursor(cur, user_id)
            if not user:
                raise LookupError("user not found")
            cur.execute("""UPDATE users
                           SET is_active=false, deactivated_reason='admin_deactivated', token_version=token_version+1
                           WHERE id=%s""", (user_id,))
            cur.execute("""INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                           VALUES (%s,'cabinlingo','user.deactivated','user',%s,'{}'::jsonb)""", (actor_id, user_id))
            updated = self._get_user_for_cursor(cur, user_id)
            if not updated:
                raise LookupError("user not found")
            return updated

    def reset_user_password(self, user_id: str, password_hash: str, actor_id: str) -> dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            user = self._get_user_for_cursor(cur, user_id)
            if not user:
                raise LookupError("user not found")
            cur.execute("""UPDATE users
                           SET password_hash=%s, password_updated_at=now(), token_version=token_version+1
                           WHERE id=%s""", (password_hash, user_id))
            cur.execute("""INSERT INTO audit_logs(actor_id,product_code,action,resource_type,resource_id,metadata)
                           VALUES (%s,'cabinlingo','user.password_reset','user',%s,'{}'::jsonb)""", (actor_id, user_id))
            updated = self._get_user_for_cursor(cur, user_id)
            if not updated:
                raise LookupError("user not found")
            return updated
