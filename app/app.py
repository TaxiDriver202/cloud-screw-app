# SPDX-FileCopyrightText: 2025 Topias Silfverhuth
# SPDX-License-Identifier: MIT

import hmac
import logging
import secrets
import sqlite3
from os import getenv

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO

from app.types import GatewayHTTPrequest, RuuviTag

_ = load_dotenv()

from app.agent import AnalysisException, analyze_trends

app = Flask(__name__)
app.secret_key = getenv("RUUVIDASH_SECRET_KEY") or secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

dbconn = sqlite3.connect(getenv("RUUVIDASH_DATABASE_PATH", "ruuvidata.db"))
cur = dbconn.cursor()
# _ = cur.execute("DROP TABLE IF EXISTS data")
_ = cur.execute(
    "CREATE TABLE IF NOT EXISTS data(mac text, temperature float, humidity float, pressure float, date timestamptz)"
)
dbconn.commit()

# Since the Ruuvi Gateway sends data very unpredictably
# This interval is just how many requests to skip before
# committing one to the database
UPDATE_INTERVAL: int = int(getenv("RUUVIDASH_UPDATE_INTERVAL", "10"))
ADMIN_PASSWORD: str | None = getenv("RUUVIDASH_PASSWORD")
ANALYSIS_PASSWORD: str | None = getenv("RUUVIDASH_PASSWORD")


def check_analysis_password() -> bool:
    """True if the request carries the correct analysis password.
    Locked out entirely (returns False) if RUUVIDASH_ANALYSIS_PASSWORD isn't set."""
    if not ANALYSIS_PASSWORD:
        return False
    supplied = request.headers.get("X-Analysis-Password", "")
    return hmac.compare_digest(supplied, ANALYSIS_PASSWORD)


updata_counter: int = 0

# Sensor display names, keyed by mac address so they don't depend on
# gateway report order. Missing entries fall back to f"tag {mac}".
tag_names: dict[str, str] = {}
RTags: dict[str, RuuviTag] = {}

# Metric slug -> (heading, unit) used by the graph page.
METRICS = {
    "temperature": ("Temperature", "°C"),
    "humidity": ("Humidity", "%"),
    "pressure": ("Pressure", "kPa"),
}

# (value, interval, button label) for the graph page range selector.
PRESETS = [
    (1, "hours", "1 hour"),
    (1, "days", "1 day"),
    (1, "weeks", "1 week"),
    (4, "weeks", "1 month"),
]

# Upper bound on points drawn per sensor; longer ranges get thinned out.
MAX_POINTS = 600


def tag_label(mac: str) -> str:
    """Display name for a sensor, falling back to its mac address."""
    return tag_names.get(mac) or f"tag {mac}"


def update_database():
    try:
        for mac, tag in RTags.items():
            cur.execute(
                "INSERT INTO data(mac, temperature, humidity, pressure, date) VALUES (?, ?, ?, ?, datetime('now', 'localtime'));",
                (mac, tag.temperature, tag.humidity, tag.pressure),
            )
        cur.execute(
            "DELETE FROM data WHERE date < datetime('now', 'localtime', '-1 years');"
        )
        dbconn.commit()
        log.info(" Inserted data into db")
    except Exception as e:
        log.error(" Data collection failed: %s" % e)


def update_data(data: dict[str, RuuviTag]) -> dict[str, dict[str, float | str]]:
    global RTags
    global updata_counter

    for mac, tag in data.items():
        RTags[mac] = RuuviTag(
            id=tag.id,
            temperature=tag.temperature or 0.0,
            humidity=tag.humidity or 0.0,
            pressure=(tag.pressure / 1000.0) or 0.0,
        )

    packets = {mac: tag.model_dump() for (mac, tag) in RTags.items()}

    updata_counter += 1
    if updata_counter > UPDATE_INTERVAL:
        update_database()
        updata_counter = 0
    socketio.emit("data_update", packets)
    return packets


"""ROUTES"""


@app.route("/graph/<item>")
def graph(item):
    try:
        if item not in METRICS:
            item = "temperature"
        metric_label, unit = METRICS[item]

        timevalue = request.args.get("value", 1, type=int)
        timevalue = max(1, min(timevalue or 1, 520))
        interval = request.args.get("interval", "hours", type=str)
        if interval not in ("hours", "days", "weeks"):
            interval = "hours"
        log.debug(f"item: {item}, timevalue: {timevalue}, interval: {interval}")

        time = timevalue
        if interval == "weeks":
            time = time * 24 * 7
        elif interval == "days":
            time = time * 24

        df = pd.read_sql(
            f"SELECT * FROM data where date > datetime('now', 'localtime', '-{time} hours');",
            dbconn,
            index_col=None,
        ).groupby("mac")

        # Initialize lists to store all data
        all_values = []
        all_tags = []

        for tag_mac, group in df:
            # ISO timestamps so the chart can lay points out on a real time axis.
            dates = (
                pd.to_datetime(group.date, errors="coerce")
                .dt.strftime("%Y-%m-%dT%H:%M:%S")
                .tolist()
            )
            values = list(zip(dates, group[item].tolist()))

            # Thin dense ranges: drawing a month of samples is unreadable and slow.
            if len(values) > MAX_POINTS:
                step = len(values) // MAX_POINTS + 1
                thinned = values[::step]
                if thinned[-1] != values[-1]:
                    thinned.append(values[-1])
                values = thinned

            all_values.append(values)
            all_tags.append(tag_label(str(tag_mac)))

        presets = [
            {
                "value": v,
                "interval": i,
                "label": label,
                "active": v == timevalue and i == interval,
            }
            for v, i, label in PRESETS
        ]
        range_label = (
            f"last {interval[:-1]}"
            if timevalue == 1
            else f"last {timevalue} {interval}"
        )

        # Tick granularity: clock times only make sense over a couple of days.
        if time <= 3:
            time_unit = "minute"
        elif time <= 48:
            time_unit = "hour"
        else:
            time_unit = "day"

        return render_template(
            "graph.html",
            all_values=all_values,
            all_tags=all_tags,
            active=item,
            metric_label=metric_label,
            unit=unit,
            value=timevalue,
            interval=interval,
            presets=presets,
            range_label=range_label,
            time_unit=time_unit,
            point_count=sum(len(v) for v in all_values),
        )
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/graph")
@app.route("/graph/")
def graph_redirect():
    return graph("temperature")


@app.route("/analyze/<item>", methods=["POST"])
def analyze_graph(item):
    """
    Runs an on-demand AI analysis over the currently displayed graph range.
    Only invoked when the user explicitly requests it from the graph page.
    """
    if not check_analysis_password():
        return jsonify({"status": "error", "message": "Invalid password"}), 401
    try:
        if item not in METRICS:
            item = "temperature"

        timevalue = request.args.get("value", 1, type=int)
        timevalue = max(1, min(timevalue or 1, 520))
        interval = request.args.get("interval", "hours", type=str)
        if interval not in ("hours", "days", "weeks"):
            interval = "hours"

        time = timevalue
        if interval == "weeks":
            time = time * 24 * 7
        elif interval == "days":
            time = time * 24

        df = pd.read_sql(
            f"SELECT mac, {item}, date FROM data where date > datetime('now', 'localtime', '-{time} hours') ORDER BY date;",
            dbconn,
        )
        if df.empty:
            return jsonify(
                {"status": "error", "message": "No data available for this range"}
            ), 400

        result = analyze_trends(df.to_csv(index=False))
        return jsonify({"status": "success", "data": result.model_dump()}), 200
    except AnalysisException as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/analyze/live", methods=["POST"])
def analyze_live():
    """
    Runs an on-demand AI analysis over the current live readings.
    Only invoked when the user explicitly requests it from the dashboard.
    """
    if not check_analysis_password():
        return jsonify({"status": "error", "message": "Invalid password"}), 401
    try:
        if not RTags:
            return jsonify(
                {"status": "error", "message": "No live readings available"}
            ), 400

        rows = [
            f"{mac},{tag_label(mac)},{tag.temperature},{tag.humidity},{tag.pressure}"
            for mac, tag in RTags.items()
        ]
        csv_data = "mac,name,temperature,humidity,pressure\n" + "\n".join(rows)

        result = analyze_trends(csv_data)
        return jsonify({"status": "success", "data": result.model_dump()}), 200
    except AnalysisException as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 502
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 500


def admin_authenticated() -> bool:
    return bool(ADMIN_PASSWORD) and session.get("admin_authenticated") is True


@app.route("/supersecretadmin", methods=["GET", "POST"])
def admin():
    global tag_names

    if request.method == "POST" and "pass" in request.form:
        passwd = request.form.get("pass", "", type=str)
        if ADMIN_PASSWORD and hmac.compare_digest(passwd, ADMIN_PASSWORD):
            session["admin_authenticated"] = True
        else:
            return render_template(
                "admin.html", active="admin", authenticated=False, login_error=True
            )
        return redirect(url_for("admin"))

    if not admin_authenticated():
        return render_template("admin.html", active="admin", authenticated=False)

    for mac in RTags:
        name = request.args.get(f"tag:{mac}", "", type=str).strip()
        if name != "":
            tag_names[mac] = name

    weeks: int | None = request.args.get("weeks", type=int)
    if weeks is not None and weeks >= 0:
        try:
            _ = cur.execute(
                f"DELETE FROM data WHERE date < datetime('now', 'localtime', '-{weeks * 7} days');"
            )
            dbconn.commit()
            log.info(f"successfully deleted data older than {weeks} weeks")
        except Exception as e:
            log.error(e)
            return jsonify({"status": "error", "message": str(e)}), 500
    return render_template(
        "admin.html",
        active="admin",
        authenticated=True,
        tags=RTags,
        tag_names=tag_names,
    )


@app.route("/supersecretadmin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin"))


@app.route("/")
@app.route("/dashboard")
def dashboard():
    data = {mac: tag.model_dump() for (mac, tag) in RTags.items()}
    return render_template(
        "dashboard.html", data=data, tag_names=tag_names, active="dashboard"
    )


@app.route("/request", methods=["POST"])
def request_data():
    """
    Receives gateway data in json and sends processed data to clients through websocket
    """
    try:
        json = request.get_json()
        print(json, "\n\n")
        gateway_req: GatewayHTTPrequest = GatewayHTTPrequest(data=json["data"])
        tags: dict[str, RuuviTag] = gateway_req.data.tags
        packets = update_data(tags)

        return jsonify({"status": "success", "data": packets}), 200
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)

# command for gunicorn(for docker place in dockerfile CMD[]):
# gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:5000 app.app:app
