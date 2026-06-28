def get_member(conn, mid):
    return conn.execute("SELECT * FROM members WHERE member_id=?", (mid,)).fetchone()


def update_member(conn, mid, **fields):
    sets = ",".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE members SET {sets} WHERE member_id=?", (*fields.values(), mid))
    conn.commit()


def add_txn(conn, mid, type_, amount, ts, actor):
    conn.execute("INSERT INTO transactions(member_id,type,amount,ts,actor) VALUES(?,?,?,?,?)",
                 (mid, type_, amount, ts, actor))
    conn.commit()


def open_fds(conn, mid):
    return conn.execute("SELECT * FROM fixed_deposits WHERE member_id=? AND closed=0", (mid,)).fetchall()


def all_open_fds(conn):
    return conn.execute("SELECT * FROM fixed_deposits WHERE closed=0").fetchall()


def get_fd(conn, fd_id):
    return conn.execute("SELECT * FROM fixed_deposits WHERE fd_id=?", (fd_id,)).fetchone()


def add_fd(conn, fd_id, mid, principal, term, rate, created_at):
    conn.execute("INSERT INTO fixed_deposits(fd_id,member_id,principal,term_minutes,rate_per_min,created_at) "
                 "VALUES(?,?,?,?,?,?)", (fd_id, mid, principal, term, rate, created_at))
    conn.commit()


def close_fd(conn, fd_id, matured):
    conn.execute("UPDATE fixed_deposits SET closed=1, matured=? WHERE fd_id=?", (1 if matured else 0, fd_id))
    conn.commit()
