import os
import sqlite3
from datetime import datetime
import config

# Try to import psycopg2 for PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


class PGConnectionWrapper:
    """Wraps psycopg2 connection to automatically translate SQLite '?' placeholders to Postgres '%s'."""
    def __init__(self, conn):
        self.conn = conn
        
    def cursor(self, *args, **kwargs):
        cur = self.conn.cursor(*args, **kwargs)
        return PGCursorWrapper(cur)
        
    def commit(self):
        return self.conn.commit()
        
    def rollback(self):
        return self.conn.rollback()
        
    def close(self):
        return self.conn.close()
        
    def __getattr__(self, name):
        return getattr(self.conn, name)


class PGCursorWrapper:
    """Wraps psycopg2 cursor to replace '?' with '%s' in SQL queries."""
    def __init__(self, cursor):
        self.cursor = cursor
        
    def execute(self, query, vars=None):
        # Automatically convert SQLite '?' placeholders to Postgres '%s'
        formatted_query = query.replace('?', '%s')
        self.cursor.execute(formatted_query, vars)
        return self  # Returns self so .fetchall() / .fetchone() work correctly immediately
        
    def __getattr__(self, name):
        return getattr(self.cursor, name)


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    
    if database_url and HAS_POSTGRES:
        # Connect to PostgreSQL and wrap it
        conn = psycopg2.connect(database_url, sslmode='require')
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return PGConnectionWrapper(conn)
    else:
        # Fallback to local SQLite database
        conn = sqlite3.connect(config.DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    conn = get_connection()
    
    if HAS_POSTGRES and os.getenv("DATABASE_URL"):
        try:
            conn.autocommit = False
        except Exception:
            pass

    cursor = conn.cursor()

    # Define auto-increment primary key based on database type
    PK_AUTO = "SERIAL PRIMARY KEY" if (os.getenv("DATABASE_URL") and HAS_POSTGRES) else "INTEGER PRIMARY KEY AUTOINCREMENT"

    try:
        # USERS
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                cbe_account TEXT DEFAULT 'Not Provided',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )

        # EKUBS
        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS ekubs (
                id {PK_AUTO},
                name TEXT NOT NULL,
                amount_per_period REAL NOT NULL,
                frequency TEXT NOT NULL,
                duration TEXT NOT NULL,
                required_members INTEGER NOT NULL,
                is_started INTEGER DEFAULT 0,
                start_date TEXT
            )
            '''
        )

        # EKUB MEMBERS
        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS ekub_members (
                id {PK_AUTO},
                ekub_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ekub_type TEXT NOT NULL,
                expected_amount REAL NOT NULL,
                order_number INTEGER NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ekub_id, user_id),
                FOREIGN KEY(ekub_id) REFERENCES ekubs(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            '''
        )

        # ACTUAL APPROVED PAYMENTS
        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS payments (
                id {PK_AUTO},
                ekub_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                period_number INTEGER NOT NULL,
                amount REAL NOT NULL,
                penalty REAL DEFAULT 0.0,
                txn_id TEXT NOT NULL UNIQUE,
                provider TEXT DEFAULT 'CBE',
                paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ekub_id) REFERENCES ekubs(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            '''
        )

        # WINNERS
        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS winners (
                id {PK_AUTO},
                ekub_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                period_number INTEGER NOT NULL,
                won_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ekub_id) REFERENCES ekubs(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            '''
        )

        # PAYMENT PARTNERS
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS payment_partners (
                user_id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            '''
        )

        # PAYMENT REQUESTS
        cursor.execute(
            f'''
            CREATE TABLE IF NOT EXISTS payment_requests (
                id {PK_AUTO},
                ekub_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                period_number INTEGER NOT NULL,
                amount REAL NOT NULL,
                penalty REAL DEFAULT 0.0,
                txn_id TEXT NOT NULL UNIQUE,
                provider TEXT DEFAULT 'CBE',
                payment_date TEXT,
                payer_name TEXT,
                receiver_name TEXT,
                extracted_amount REAL,
                verification_message TEXT,
                receipt_path TEXT,
                bank_link TEXT,
                assigned_partner_id INTEGER,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                rejection_reason TEXT,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(ekub_id) REFERENCES ekubs(id),
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(assigned_partner_id) REFERENCES users(user_id),
                FOREIGN KEY(reviewed_by) REFERENCES users(user_id)
            )
            '''
        )

        conn.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


# ============================================================
# USERS
# ============================================================

def get_user(user_id):
    conn = get_connection()
    user = conn.cursor().execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return user


def get_all_users():
    conn = get_connection()
    users = conn.cursor().execute(
        "SELECT * FROM users ORDER BY registered_at ASC"
    ).fetchall()
    conn.close()
    return users


def register_user(
    user_id,
    name,
    phone,
    cbe_account
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        INSERT OR REPLACE INTO users
        (user_id, full_name, phone, cbe_account)
        VALUES (?, ?, ?, ?)
        ''',
        (
            user_id,
            name,
            phone,
            cbe_account
        )
    )
    conn.commit()
    conn.close()


def update_user_info(
    user_id,
    name,
    phone,
    cbe_account
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        UPDATE users
        SET full_name = ?,
            phone = ?,
            cbe_account = ?
        WHERE user_id = ?
        ''',
        (
            name,
            phone,
            cbe_account,
            user_id
        )
    )
    conn.commit()
    conn.close()


# ============================================================
# EKUB
# ============================================================

def create_ekub(
    name,
    amount,
    frequency,
    duration,
    required_members
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        INSERT INTO ekubs
        (
            name,
            amount_per_period,
            frequency,
            duration,
            required_members
        )
        VALUES (?, ?, ?, ?, ?)
        ''',
        (
            name,
            amount,
            frequency,
            duration,
            required_members
        )
    )
    conn.commit()
    conn.close()


def update_ekub_info(
    ekub_id,
    name,
    amount
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        UPDATE ekubs
        SET name = ?,
            amount_per_period = ?
        WHERE id = ?
        ''',
        (
            name,
            amount,
            ekub_id
        )
    )
    conn.commit()
    conn.close()


def update_ekub_duration(
    ekub_id,
    duration_str,
    required_members
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        UPDATE ekubs
        SET duration = ?,
            required_members = ?
        WHERE id = ?
        ''',
        (
            duration_str,
            required_members,
            ekub_id
        )
    )
    conn.commit()
    conn.close()


def get_all_ekubs():
    conn = get_connection()
    ekubs = conn.cursor().execute(
        "SELECT * FROM ekubs"
    ).fetchall()
    conn.close()
    return ekubs


def get_ekub(ekub_id):
    conn = get_connection()
    ekub = conn.cursor().execute(
        "SELECT * FROM ekubs WHERE id = ?",
        (ekub_id,)
    ).fetchone()
    conn.close()
    return ekub


def get_ekub_total_shares(ekub_id):
    conn = get_connection()
    members = conn.cursor().execute(
        '''
        SELECT ekub_type
        FROM ekub_members
        WHERE ekub_id = ?
        ''',
        (ekub_id,)
    ).fetchall()
    conn.close()

    total = 0.0
    for m in members:
        if m['ekub_type'] == 'Full':
            total += 1.0
        elif m['ekub_type'] == 'Half':
            total += 0.5
        elif m['ekub_type'] == '1/4':
            total += 0.25
    return total


def start_ekub(ekub_id):
    conn = get_connection()
    start_date = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )
    conn.cursor().execute(
        '''
        UPDATE ekubs
        SET is_started = 1,
            start_date = ?
        WHERE id = ?
        ''',
        (
            start_date,
            ekub_id
        )
    )
    conn.commit()
    conn.close()


# ============================================================
# MEMBERS
# ============================================================

def join_ekub(
    ekub_id,
    user_id,
    ekub_type,
    expected_amount
):
    conn = get_connection()
    cursor = conn.cursor()

    row = cursor.execute(
        '''
        SELECT COUNT(*) as cnt
        FROM ekub_members
        WHERE ekub_id = ?
        ''',
        (ekub_id,)
    ).fetchone()
    
    order_num = (row['cnt'] if isinstance(row, dict) else row[0]) + 1

    cursor.execute(
        '''
        INSERT INTO ekub_members
        (
            ekub_id,
            user_id,
            ekub_type,
            expected_amount,
            order_number
        )
        VALUES (?, ?, ?, ?, ?)
        ''',
        (
            ekub_id,
            user_id,
            ekub_type,
            expected_amount,
            order_num
        )
    )
    conn.commit()
    conn.close()
    return order_num


def remove_ekub_member(
    ekub_id,
    user_id
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        DELETE FROM ekub_members
        WHERE ekub_id = ?
        AND user_id = ?
        ''',
        (
            ekub_id,
            user_id
        )
    )
    conn.commit()
    conn.close()


def get_ekub_members(ekub_id):
    conn = get_connection()
    members = conn.cursor().execute(
        '''
        SELECT
            em.*,
            u.full_name,
            u.phone,
            u.cbe_account
        FROM ekub_members em
        JOIN users u
            ON em.user_id = u.user_id
        WHERE em.ekub_id = ?
        ORDER BY em.order_number ASC
        ''',
        (ekub_id,)
    ).fetchall()
    conn.close()
    return members


def get_ekub_member_by_phone(
    ekub_id,
    phone
):
    conn = get_connection()
    member = conn.cursor().execute(
        '''
        SELECT
            em.user_id,
            u.full_name,
            u.phone
        FROM ekub_members em
        JOIN users u
            ON em.user_id = u.user_id
        WHERE em.ekub_id = ?
        AND u.phone LIKE ?
        ''',
        (
            ekub_id,
            f"%{phone.strip()}%"
        )
    ).fetchone()
    conn.close()
    return member


def get_user_memberships(user_id):
    conn = get_connection()
    memberships = conn.cursor().execute(
        '''
        SELECT
            em.*,
            e.name AS ekub_name,
            e.duration,
            e.required_members
        FROM ekub_members em
        JOIN ekubs e
            ON em.ekub_id = e.id
        WHERE em.user_id = ?
        ''',
        (user_id,)
    ).fetchall()
    conn.close()
    return memberships


# ============================================================
# PERIODS / PAYMENTS
# ============================================================

def get_period_payment_by_user(
    user_id,
    ekub_id,
    period_num
):
    conn = get_connection()
    pmt = conn.cursor().execute(
        '''
        SELECT *
        FROM payments
        WHERE user_id = ?
        AND ekub_id = ?
        AND period_number = ?
        ''',
        (
            user_id,
            ekub_id,
            period_num
        )
    ).fetchone()
    conn.close()
    return pmt


def get_next_unpaid_period(
    user_id,
    ekub_id
):
    conn = get_connection()
    payments = conn.cursor().execute(
        '''
        SELECT period_number
        FROM payments
        WHERE user_id = ?
        AND ekub_id = ?
        ''',
        (
            user_id,
            ekub_id
        )
    ).fetchall()
    conn.close()

    paid_periods = {
        p['period_number']
        for p in payments
    }

    period = 1
    while period in paid_periods:
        period += 1
    return period


def get_ekub_period_days(ekub_id):
    ekub = get_ekub(ekub_id)
    if not ekub:
        return 7
    return {
        "Daily": 1,
        "Weekly": 7,
        "Monthly": 30,
    }.get(ekub['frequency'], 7)


def get_current_ekub_period(ekub_id):
    ekub = get_ekub(ekub_id)
    if not ekub or not ekub['is_started']:
        return 1

    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT MAX(period_number) AS last_period
        FROM winners
        WHERE ekub_id = ?
        ''',
        (ekub_id,)
    ).fetchone()
    conn.close()

    last_period = (
        row['last_period']
        if row and row['last_period'] is not None
        else 0
    )
    return last_period + 1


def is_txn_exists(txn_id):
    conn = get_connection()
    exists = conn.cursor().execute(
        '''
        SELECT 1
        FROM payments
        WHERE txn_id = ?
        ''',
        (txn_id,)
    ).fetchone() is not None
    conn.close()
    return exists


def record_payment(
    ekub_id,
    user_id,
    period_number,
    amount,
    penalty,
    txn_id,
    provider="CBE"
):
    return False, "Automatic payment approval is disabled. Please use manual partner approval."


def get_period_pending_request_count(
    ekub_id,
    period_num
):
    conn = get_connection()
    row = conn.cursor().execute(
        """
        SELECT COUNT(*) as cnt
        FROM payment_requests
        WHERE ekub_id = ?
        AND period_number = ?
        AND status = 'pending'
        """,
        (
            ekub_id,
            period_num
        )
    ).fetchone()
    conn.close()
    return row['cnt'] if isinstance(row, dict) else row[0]


def get_period_paid_count(
    ekub_id,
    period_num
):
    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT COUNT(DISTINCT user_id) as cnt
        FROM payments
        WHERE ekub_id = ?
        AND period_number = ?
        ''',
        (
            ekub_id,
            period_num
        )
    ).fetchone()
    conn.close()
    return row['cnt'] if isinstance(row, dict) else row[0]


def get_user_payments(
    user_id,
    ekub_id
):
    conn = get_connection()
    payments = conn.cursor().execute(
        '''
        SELECT *
        FROM payments
        WHERE user_id = ?
        AND ekub_id = ?
        ORDER BY period_number ASC
        ''',
        (
            user_id,
            ekub_id
        )
    ).fetchall()
    conn.close()
    return payments


# ============================================================
# WINNERS
# ============================================================

def get_ekub_winners(ekub_id):
    conn = get_connection()
    winners = conn.cursor().execute(
        '''
        SELECT *
        FROM winners
        WHERE ekub_id = ?
        ''',
        (ekub_id,)
    ).fetchall()
    conn.close()
    return winners


def get_period_winner(
    ekub_id,
    period_num
):
    conn = get_connection()
    winner = conn.cursor().execute(
        '''
        SELECT *
        FROM winners
        WHERE ekub_id = ?
        AND period_number = ?
        ''',
        (
            ekub_id,
            period_num
        )
    ).fetchone()
    conn.close()
    return winner


def add_winner(
    ekub_id,
    user_id,
    period_number
):
    conn = get_connection()
    conn.cursor().execute(
        '''
        INSERT INTO winners
        (
            ekub_id,
            user_id,
            period_number
        )
        VALUES (?, ?, ?)
        ''',
        (
            ekub_id,
            user_id,
            period_number
        )
    )
    conn.commit()
    conn.close()


# ============================================================
# PAYMENT PARTNERS
# ============================================================

def add_payment_partner(user_id):
    conn = get_connection()
    conn.cursor().execute(
        '''
        INSERT OR REPLACE INTO payment_partners
        (
            user_id,
            active
        )
        VALUES (?, 1)
        ''',
        (user_id,)
    )
    conn.commit()
    conn.close()


def remove_payment_partner(user_id):
    conn = get_connection()
    conn.cursor().execute(
        '''
        UPDATE payment_partners
        SET active = 0
        WHERE user_id = ?
        ''',
        (user_id,)
    )
    conn.commit()
    conn.close()


def is_payment_partner(user_id):
    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT 1
        FROM payment_partners
        WHERE user_id = ?
        AND active = 1
        ''',
        (user_id,)
    ).fetchone()
    conn.close()
    return row is not None


def get_payment_partners():
    conn = get_connection()
    rows = conn.cursor().execute(
        '''
        SELECT
            pp.user_id,
            pp.created_at,
            u.full_name,
            u.phone
        FROM payment_partners pp
        JOIN users u
            ON u.user_id = pp.user_id
        WHERE pp.active = 1
        ORDER BY u.full_name
        '''
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# PAYMENT REQUEST
# ============================================================

def create_payment_request(
    ekub_id,
    user_id,
    period_number,
    amount,
    penalty,
    txn_id,
    provider,
    payment_date,
    payer_name,
    receiver_name,
    extracted_amount,
    verification_message,
    receipt_path=None,
    bank_link=None
):
    conn = get_connection()
    cur = conn.cursor()

    partner = cur.execute(
        '''
        SELECT user_id
        FROM payment_partners
        WHERE active = 1
        ORDER BY created_at ASC
        LIMIT 1
        '''
    ).fetchone()

    partner_id = (
        partner['user_id']
        if partner
        else None
    )

    cur.execute(
        '''
        INSERT INTO payment_requests
        (
            ekub_id,
            user_id,
            period_number,
            amount,
            penalty,
            txn_id,
            provider,
            payment_date,
            payer_name,
            receiver_name,
            extracted_amount,
            verification_message,
            receipt_path,
            bank_link,
            assigned_partner_id,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''',
        (
            ekub_id,
            user_id,
            period_number,
            amount,
            penalty,
            txn_id,
            provider,
            payment_date,
            payer_name,
            receiver_name,
            extracted_amount,
            verification_message,
            receipt_path,
            bank_link,
            partner_id
        )
    )

    request_id = None
    if not (HAS_POSTGRES and os.getenv("DATABASE_URL")):
        try:
            request_id = cur.lastrowid
        except Exception:
            pass

    conn.commit()
    conn.close()
    return request_id


def get_pending_payment_requests(partner_id=None):
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute(
        '''
        SELECT
            pr.*,
            u.full_name AS member_name,
            u.phone AS member_phone,
            e.name AS ekub_name,
            em.ekub_type AS ekub_type
        FROM payment_requests pr
        JOIN users u
            ON u.user_id = pr.user_id
        JOIN ekubs e
            ON e.id = pr.ekub_id
        LEFT JOIN ekub_members em
            ON em.ekub_id = pr.ekub_id
            AND em.user_id = pr.user_id
        WHERE pr.status = 'pending'
        ORDER BY pr.submitted_at ASC
        '''
    ).fetchall()
    conn.close()
    return rows


def get_pending_payment_for_period(
    user_id,
    ekub_id,
    period_number
):
    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT *
        FROM payment_requests
        WHERE user_id = ?
        AND ekub_id = ?
        AND period_number = ?
        AND status = 'pending'
        LIMIT 1
        ''',
        (
            user_id,
            ekub_id,
            period_number
        )
    ).fetchone()
    conn.close()
    return row


def get_payment_request(request_id):
    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT *
        FROM payment_requests
        WHERE id = ?
        ''',
        (request_id,)
    ).fetchone()
    conn.close()
    return row


def get_payment_request_by_txn_id(txn_id):
    conn = get_connection()
    row = conn.cursor().execute(
        '''
        SELECT *
        FROM payment_requests
        WHERE txn_id = ?
        ''',
        (txn_id,)
    ).fetchone()
    conn.close()
    return row


# ============================================================
# MANUAL APPROVAL
# ============================================================

def approve_payment_request(
    request_id,
    reviewer_id
):
    conn = get_connection()
    cur = conn.cursor()

    partner = cur.execute(
        '''
        SELECT 1
        FROM payment_partners
        WHERE user_id = ?
        AND active = 1
        ''',
        (reviewer_id,)
    ).fetchone()

    if not partner:
        conn.close()
        return False, "You are not an active Payment Approval Partner."

    row = cur.execute(
        '''
        SELECT *
        FROM payment_requests
        WHERE id = ?
        ''',
        (request_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False, "Payment request was not found."

    if row['status'] != 'pending':
        conn.close()
        return False, f"This payment is already {row['status']}."

    existing_txn = cur.execute(
        '''
        SELECT 1
        FROM payments
        WHERE txn_id = ?
        ''',
        (row['txn_id'],)
    ).fetchone()

    if existing_txn:
        cur.execute(
            '''
            UPDATE payment_requests
            SET status = 'rejected',
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                rejection_reason = ?
            WHERE id = ?
            ''',
            (
                reviewer_id,
                'Transaction was already recorded.',
                request_id
            )
        )
        conn.commit()
        conn.close()
        return False, "Transaction was already recorded."

    existing_period = cur.execute(
        '''
        SELECT 1
        FROM payments
        WHERE ekub_id = ?
        AND user_id = ?
        AND period_number = ?
        ''',
        (
            row['ekub_id'],
            row['user_id'],
            row['period_number']
        )
    ).fetchone()

    if existing_period:
        cur.execute(
            '''
            UPDATE payment_requests
            SET status = 'rejected',
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                rejection_reason = ?
            WHERE id = ?
            ''',
            (
                reviewer_id,
                'This member already has a payment recorded for this period.',
                request_id
            )
        )
        conn.commit()
        conn.close()
        return False, "This member already has a payment recorded for this period."

    paid_at = (
        row['payment_date']
        if row['payment_date']
        else datetime.now().strftime(
            '%Y-%m-%d %H:%M:%S'
        )
    )

    cur.execute(
        '''
        INSERT INTO payments
        (
            ekub_id,
            user_id,
            period_number,
            amount,
            penalty,
            txn_id,
            provider,
            paid_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            row['ekub_id'],
            row['user_id'],
            row['period_number'],
            row['amount'],
            row['penalty'],
            row['txn_id'],
            row['provider'],
            paid_at
        )
    )

    cur.execute(
        '''
        UPDATE payment_requests
        SET status = 'approved',
            reviewed_by = ?,
            reviewed_at = CURRENT_TIMESTAMP,
            rejection_reason = NULL
        WHERE id = ?
        ''',
        (
            reviewer_id,
            request_id
        )
    )

    conn.commit()
    conn.close()
    return True, 'Payment approved.'


def update_payment_receipt_path(request_id, receipt_path):
    conn = get_connection()
    conn.cursor().execute(
        """
        UPDATE payment_requests
        SET receipt_path = ?
        WHERE id = ?
        """,
        (receipt_path, request_id)
    )
    conn.commit()
    conn.close()


# ============================================================
# MANUAL REJECTION
# ============================================================

def reject_payment_request(
    request_id,
    reviewer_id,
    reason='Rejected by payment approval partner.'
):
    conn = get_connection()
    cur = conn.cursor()

    partner = cur.execute(
        '''
        SELECT 1
        FROM payment_partners
        WHERE user_id = ?
        AND active = 1
        ''',
        (reviewer_id,)
    ).fetchone()

    if not partner:
        conn.close()
        return False, "You are not an active Payment Approval Partner."

    row = cur.execute(
        '''
        SELECT status
        FROM payment_requests
        WHERE id = ?
        ''',
        (request_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False, "Payment request was not found."

    if row['status'] != 'pending':
        conn.close()
        return False, f"This payment is already {row['status']}."

    cur.execute(
        '''
        UPDATE payment_requests
        SET status = 'rejected',
            reviewed_by = ?,
            reviewed_at = CURRENT_TIMESTAMP,
            rejection_reason = ?
        WHERE id = ?
        ''',
        (
            reviewer_id,
            reason,
            request_id
        )
    )
    conn.commit()
    conn.close()
    return True, 'Payment rejected.'


# ============================================================
# USER PAYMENT REQUEST HISTORY
# ============================================================

def get_user_payment_requests(
    user_id,
    ekub_id=None
):
    conn = get_connection()
    if ekub_id is None:
        rows = conn.cursor().execute(
            '''
            SELECT *
            FROM payment_requests
            WHERE user_id = ?
            ORDER BY submitted_at DESC
            ''',
            (user_id,)
        ).fetchall()
    else:
        rows = conn.cursor().execute(
            '''
            SELECT *
            FROM payment_requests
            WHERE user_id = ?
            AND ekub_id = ?
            ORDER BY submitted_at DESC
            ''',
            (
                user_id,
                ekub_id
            )
        ).fetchall()
    conn.close()
    return rows
