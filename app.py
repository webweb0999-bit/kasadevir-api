"""
KASADEVIR API Sunucusu
Powered by Erdem KAYA
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_URL = os.environ.get("DATABASE_URL", "")
API_KEY = os.environ.get("API_KEY", "kasadevir_2024_EK_gizli")

def get_db():
    conn = psycopg2.connect(DB_URL)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def setup_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vardiyalar (
            id              SERIAL PRIMARY KEY,
            vardiya_no      TEXT NOT NULL,
            tarih           TEXT NOT NULL,
            acilis_zaman    TEXT NOT NULL DEFAULT \'\',
            kapanis_zaman   TEXT,
            devreden        TEXT NOT NULL DEFAULT \'\',
            devralan        TEXT NOT NULL DEFAULT \'\',
            devir_nakit     REAL NOT NULL DEFAULT 0,
            toplam_gider    REAL NOT NULL DEFAULT 0,
            sayilan_nakit   REAL,
            peron_nakit     REAL DEFAULT 0,
            beklenen_nakit  REAL,
            fark            REAL,
            durum           TEXT NOT NULL DEFAULT \'acik\'
        );
        CREATE TABLE IF NOT EXISTS giderler (
            id          SERIAL PRIMARY KEY,
            vardiya_id  INTEGER NOT NULL,
            zaman       TEXT NOT NULL,
            kategori    TEXT NOT NULL,
            tutar       REAL NOT NULL,
            aciklama    TEXT DEFAULT \'\'
        );
        CREATE TABLE IF NOT EXISTS calisanlar (
            id    SERIAL PRIMARY KEY,
            isim  TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS urun_talepleri (
            id         SERIAL PRIMARY KEY,
            zaman      TEXT NOT NULL,
            urun_adi   TEXT NOT NULL,
            soran      TEXT DEFAULT \'\',
            not_metni  TEXT DEFAULT \'\',
            durum      TEXT NOT NULL DEFAULT \'bekliyor\'
        );
        CREATE TABLE IF NOT EXISTS islem_logu (
            id      SERIAL PRIMARY KEY,
            zaman   TEXT NOT NULL,
            islem   TEXT NOT NULL,
            detay   TEXT NOT NULL DEFAULT \'\'
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

def auth(req):
    return req.headers.get("X-API-Key") == API_KEY

# ── SAĞLIK KONTROLÜ ──
@app.route("/")
def index():
    return jsonify({"status": "ok", "app": "KASADEVIR API", "powered_by": "Erdem KAYA"})

@app.route("/health")
def health():
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT 1"); conn.close()
        return jsonify({"status": "ok", "db": "connected"})
    except Exception as e:
        return jsonify({"status": "error", "db": str(e)}), 500

# ── VARDİYALAR ──
@app.route("/api/vardiyalar", methods=["GET"])
def vardiyalar_listele():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        tarih  = request.args.get("tarih")
        durum  = request.args.get("durum")
        limit  = int(request.args.get("limit", 500))
        sorgu  = "SELECT * FROM vardiyalar WHERE 1=1"
        params = []
        if tarih: sorgu += " AND tarih=%s"; params.append(tarih)
        if durum: sorgu += " AND durum=%s"; params.append(durum)
        sorgu += " ORDER BY id DESC LIMIT %s"; params.append(limit)
        cur.execute(sorgu, params)
        rows = cur.fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/vardiyalar", methods=["POST"])
def vardiya_ekle():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO vardiyalar
            (vardiya_no,tarih,acilis_zaman,devreden,devralan,devir_nakit,toplam_gider,durum,peron_nakit)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (d["vardiya_no"],d["tarih"],d.get("acilis_zaman",""),
              d["devreden"],d["devralan"],d.get("devir_nakit",0),
              d.get("toplam_gider",0),d.get("durum","acik"),d.get("peron_nakit",0)))
        yeni_id = cur.fetchone()["id"]
        conn.commit(); conn.close()
        return jsonify({"id": yeni_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/vardiyalar/<int:vid>", methods=["GET"])
def vardiya_getir(vid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM vardiyalar WHERE id=%s", (vid,))
        row = cur.fetchone(); conn.close()
        if row: return jsonify(dict(row))
        return jsonify({"error": "Bulunamadi"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/vardiyalar/<int:vid>", methods=["PATCH"])
def vardiya_guncelle(vid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        alanlar = ", ".join([f"{k}=%s" for k in d.keys()])
        cur.execute(f"UPDATE vardiyalar SET {alanlar} WHERE id=%s",
                    list(d.values()) + [vid])
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/vardiyalar/<int:vid>", methods=["DELETE"])
def vardiya_sil(vid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM giderler WHERE vardiya_id=%s", (vid,))
        cur.execute("DELETE FROM vardiyalar WHERE id=%s", (vid,))
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── GİDERLER ──
@app.route("/api/giderler", methods=["GET"])
def giderler_listele():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        vid   = request.args.get("vardiya_id")
        limit = int(request.args.get("limit", 300))
        if vid:
            cur.execute("SELECT * FROM giderler WHERE vardiya_id=%s ORDER BY id", (vid,))
        else:
            cur.execute("SELECT * FROM giderler ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/giderler", methods=["POST"])
def gider_ekle():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO giderler (vardiya_id,zaman,kategori,tutar,aciklama)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (d["vardiya_id"],d.get("zaman",datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
              d["kategori"],d["tutar"],d.get("aciklama","")))
        yeni_id = cur.fetchone()["id"]
        # Vardiya toplam gider guncelle
        cur.execute("UPDATE vardiyalar SET toplam_gider=(SELECT COALESCE(SUM(tutar),0) FROM giderler WHERE vardiya_id=%s) WHERE id=%s",
                    (d["vardiya_id"], d["vardiya_id"]))
        conn.commit(); conn.close()
        return jsonify({"id": yeni_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/giderler/<int:gid>", methods=["PATCH"])
def gider_guncelle(gid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        alanlar = ", ".join([f"{k}=%s" for k in d.keys()])
        cur.execute(f"UPDATE giderler SET {alanlar} WHERE id=%s",
                    list(d.values()) + [gid])
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/giderler/<int:gid>", methods=["DELETE"])
def gider_sil(gid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT vardiya_id FROM giderler WHERE id=%s", (gid,))
        row = cur.fetchone()
        cur.execute("DELETE FROM giderler WHERE id=%s", (gid,))
        if row:
            vid = row["vardiya_id"]
            cur.execute("UPDATE vardiyalar SET toplam_gider=(SELECT COALESCE(SUM(tutar),0) FROM giderler WHERE vardiya_id=%s) WHERE id=%s",
                        (vid, vid))
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── ÇALIŞANLAR ──
@app.route("/api/calisanlar", methods=["GET"])
def calisanlar_listele():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM calisanlar ORDER BY isim")
        rows = cur.fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/calisanlar", methods=["POST"])
def calisan_ekle():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO calisanlar (isim) VALUES (%s) RETURNING id", (d["isim"],))
        yeni_id = cur.fetchone()["id"]
        conn.commit(); conn.close()
        return jsonify({"id": yeni_id}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Zaten var"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/calisanlar/<int:cid>", methods=["DELETE"])
def calisan_sil(cid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM calisanlar WHERE id=%s", (cid,))
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── ÜRÜN TALEPLERİ ──
@app.route("/api/urun_talepleri", methods=["GET"])
def urun_talepleri():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        durum = request.args.get("durum")
        limit = int(request.args.get("limit", 200))
        if durum:
            cur.execute("SELECT * FROM urun_talepleri WHERE durum=%s ORDER BY id DESC LIMIT %s", (durum, limit))
        else:
            cur.execute("SELECT * FROM urun_talepleri ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/urun_talepleri", methods=["POST"])
def urun_ekle():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO urun_talepleri (zaman,urun_adi,soran,not_metni) VALUES (%s,%s,%s,%s) RETURNING id",
                    (d.get("zaman",datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                     d["urun_adi"],d.get("soran",""),d.get("not_metni","")))
        yeni_id = cur.fetchone()["id"]
        conn.commit(); conn.close()
        return jsonify({"id": yeni_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/urun_talepleri/<int:uid>", methods=["PATCH"])
def urun_guncelle(uid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("UPDATE urun_talepleri SET durum=%s WHERE id=%s", (d["durum"], uid))
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/urun_talepleri/<int:uid>", methods=["DELETE"])
def urun_sil(uid):
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM urun_talepleri WHERE id=%s", (uid,))
        conn.commit(); conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── İŞLEM LOGU ──
@app.route("/api/islem_logu", methods=["GET"])
def log_listele():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        conn = get_db(); cur = conn.cursor()
        limit = int(request.args.get("limit", 200))
        cur.execute("SELECT * FROM islem_logu ORDER BY id DESC LIMIT %s", (limit,))
        rows = cur.fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/islem_logu", methods=["POST"])
def log_ekle():
    if not auth(request): return jsonify({"error": "Yetkisiz"}), 401
    try:
        d = request.json; conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO islem_logu (zaman,islem,detay) VALUES (%s,%s,%s)",
                    (d.get("zaman",datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                     d["islem"],d.get("detay","")))
        conn.commit(); conn.close()
        return jsonify({"ok": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    setup_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
