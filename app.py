from email_checker import (
    clean_email_address,
    clean_app_password,
    check_all_mailboxes
)
import plotly.graph_objects as go
import plotly.express as px
from pymongo import MongoClient
from datetime import datetime, timedelta
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import ast
import os


load_dotenv()

# ============================================================
# MONGODB
# ============================================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "inbox_test"


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


def load_accounts():
    docs = list(get_db()["accounts"].find({}, {"_id": 0}))
    for d in docs:
        if "enabled" not in d:
            d["enabled"] = True
    return docs


def save_accounts(accounts):
    db = get_db()
    db["accounts"].delete_many({})
    if accounts:
        db["accounts"].insert_many(accounts)


def load_domains():
    docs = list(get_db()["domains"].find({}, {"_id": 0}))
    result = []
    for d in docs:
        if isinstance(d, dict):
            if "enabled" not in d:
                d["enabled"] = True
            result.append(d)
        else:
            result.append({"domain": d, "enabled": True})
    return result


def save_domains(domains):
    db = get_db()
    db["domains"].delete_many({})
    if domains:
        to_insert = []
        for d in domains:
            if isinstance(d, dict):
                to_insert.append(d)
            else:
                to_insert.append({"domain": d, "enabled": True})
        db["domains"].insert_many(to_insert)


def get_results_collection():
    return get_db()["placement_results"]


def load_placement_results(start_dt: datetime, end_dt: datetime):
    """Load results and keep only the LATEST record per domain + seed_email"""
    collection = get_results_collection()
    start_str = start_dt.strftime("%Y-%m-%d 00:00:00")
    end_str = end_dt.strftime("%Y-%m-%d 23:59:59")

    cursor = collection.find(
        {"date": {"$gte": start_str, "$lte": end_str}},
        {"_id": 0}
    )
    all_results = list(cursor)

    if not all_results:
        return []

    # Convert to DataFrame to easily keep only the latest record
    df = pd.DataFrame(all_results)

    # Ensure date is sortable
    df["date"] = pd.to_datetime(df["date"])

    # Keep only the latest record for each domain + seed_email combination
    df = df.sort_values("date").drop_duplicates(
        subset=["domain", "seed_email"],
        keep="last"
    )

    return df.to_dict("records")


# ============================================================
# PAGE CONFIG + CSS
# ============================================================
st.set_page_config(
    page_title="Inbox Placement Tester",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1200px;}
    
    .metric-card {
        background: white; border: 1px solid #e5e7eb; border-radius: 12px;
        padding: 1.1rem 1.25rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04); height: 100%;
    }
    .metric-label {font-size: 0.85rem; color: #6b7280; margin-bottom: 0.35rem;
                   display: flex; justify-content: space-between; align-items: center;}
    .metric-value {font-size: 1.75rem; font-weight: 700; color: #111827; line-height: 1.2;}
    .metric-sub {font-size: 0.75rem; color: #9ca3af; margin-top: 0.25rem;}
    
    .section-title {font-size: 1.35rem; font-weight: 700; color: #111827;
                    display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;}
    
    .stButton > button {border-radius: 8px; font-weight: 600;}
    
    .domain-header {
        font-weight: 600;
        color: #374151;
        font-size: 0.9rem;
        padding-bottom: 8px;
        border-bottom: 1px solid #e5e7eb;
        margin-bottom: 4px;
    }
    .inbox-badge {
        background: #d1fae5;
        color: #065f46;
        padding: 5px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    .spam-badge {
        background: #fee2e2;
        color: #991b1b;
        padding: 5px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION STATE
# ============================================================
if "accounts" not in st.session_state:
    st.session_state.accounts = load_accounts()
if "domains" not in st.session_state:
    st.session_state.domains = load_domains()
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "show_live_results" not in st.session_state:
    st.session_state.show_live_results = False

if st.session_state.get("force_today"):
    st.session_state.dash_range = "Today (1 day)"
    st.session_state.dash_date = datetime.now().date()
    st.session_state.force_today = False
    st.session_state.show_live_results = False
    if "live_df" in st.session_state:
        del st.session_state.live_df
    if "live_errors" in st.session_state:
        del st.session_state.live_errors

accounts = st.session_state.accounts
domains = st.session_state.domains

enabled_accounts = [a for a in accounts if a.get("enabled", True)]
enabled_domains = [
    d["domain"] if isinstance(d, dict) else d
    for d in domains
    if (d.get("enabled", True) if isinstance(d, dict) else True)
]


# ============================================================
# TOP NAVIGATION
# ============================================================
st.markdown("""
<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.75rem;">
    <span style="font-size:1.5rem;">📧</span>
    <span style="font-size:1.45rem;font-weight:700;color:#111827;">Inbox Placement Tester</span>
</div>
""", unsafe_allow_html=True)

nav_cols = st.columns([1, 1, 1, 6])
pages = [("Dashboard", "🏠"), ("Accounts", "👥"), ("Domains", "🌐")]

for i, (name, icon) in enumerate(pages):
    with nav_cols[i]:
        is_active = st.session_state.page == name
        if st.button(f"{icon} {name}", key=f"nav_{name}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.page = name
            st.rerun()

st.markdown("<hr style='margin:1rem 0 1.5rem 0;border:none;border-top:1px solid #e5e7eb;'>",
            unsafe_allow_html=True)


# ============================================================
# PAGE: DASHBOARD
# ============================================================
if st.session_state.page == "Dashboard":
    st.markdown('<div class="section-title">📊 Dashboard</div>',
                unsafe_allow_html=True)

    col_date, col_range, col_apply, col_today = st.columns([2, 2, 1, 1])

    with col_date:
        selected_date = st.date_input(
            "Date",
            value=st.session_state.get("dash_date", datetime.now().date()),
            key="dash_date"
        )

    with col_range:
        range_option = st.selectbox(
            "Range",
            options=["Today (1 day)", "Yesterday (1 day)",
                     "Last 7 days", "Custom"],
            key="dash_range"
        )

    today = datetime.now().date()
    if range_option == "Today (1 day)":
        start_date = end_date = today
    elif range_option == "Yesterday (1 day)":
        start_date = end_date = today - timedelta(days=1)
    elif range_option == "Last 7 days":
        start_date = today - timedelta(days=6)
        end_date = today
    else:
        start_date = end_date = selected_date

    with col_apply:
        st.write("")
        if st.button("Apply", type="primary", use_container_width=True):
            st.session_state.show_live_results = False
            if "live_df" in st.session_state:
                del st.session_state.live_df
            if "live_errors" in st.session_state:
                del st.session_state.live_errors
            st.rerun()

    with col_today:
        st.write("")
        if st.button("Today", use_container_width=True):
            st.session_state.force_today = True
            st.rerun()

    # LIVE RESULTS
    if st.session_state.get("show_live_results") and "live_df" in st.session_state:
        df = st.session_state.live_df
        errors = st.session_state.get("live_errors", [])

        st.success("✅ Showing *current* placement test results")

        if errors:
            st.warning(f"{len(errors)} mailbox(es) failed")
            st.dataframe(pd.DataFrame(errors),
                         use_container_width=True, hide_index=True)

        mailbox_level = df.groupby("Mailbox").agg(
            Inbox=("Inbox", "max"), Spam=("Spam", "max")).reset_index()
        total_inbox_live = int(mailbox_level["Inbox"].sum())
        total_spam_live = int(mailbox_level["Spam"].sum())
        total_all_live = total_inbox_live + total_spam_live

        m1, m2, m3, m4, m5 = st.columns(5)
        for col, label, value, sub, icon in [
            (m1, "Accounts", len(enabled_accounts), "Enabled mailboxes", "👥"),
            (m2, "Domains", len(enabled_domains), "Enabled domains", "🌐"),
            (m3, "Inbox", total_inbox_live, "Total INBOX (this run)", "📥"),
            (m4, "Spam", total_spam_live, "Total Spam (this run)", "🚫"),
            (m5, "All-mail", total_all_live, "Total All Mail (this run)", "📧"),
        ]:
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label} <span>{icon}</span></div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)

        st.subheader("🌐 Domain Summary")
        domain_summary = df.groupby("Domain").agg(
            Inbox=("Inbox", "sum"), Spam=("Spam", "sum")).reset_index()
        domain_summary["Total"] = domain_summary["Inbox"] + \
            domain_summary["Spam"]
        domain_summary["Inbox %"] = (
            domain_summary["Inbox"] / domain_summary["Total"].replace(0, 1) * 100).round(2)
        domain_summary["Spam %"] = (
            domain_summary["Spam"] / domain_summary["Total"].replace(0, 1) * 100).round(2)
        st.dataframe(domain_summary[["Domain", "Inbox", "Spam", "Total", "Inbox %", "Spam %"]],
                     use_container_width=True, hide_index=True)

        st.subheader("📋 Detailed Results")
        st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("← Back to History View"):
            st.session_state.show_live_results = False
            if "live_df" in st.session_state:
                del st.session_state.live_df
            st.rerun()

        st.markdown("---")
        st.markdown("### 📈 Visualization (Current Run)")
        c1, c2 = st.columns(2)
        with c1:
            fig = px.pie(
                pd.DataFrame({"Type": ["Inbox", "Spam"], "Count": [
                             total_inbox_live, total_spam_live]}),
                values="Count", names="Type", color="Type",
                color_discrete_map={"Inbox": "#10b981", "Spam": "#ef4444"},
                title="Overall Inbox vs Spam", hole=0.45
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            domain_df = df.groupby("Domain").agg(
                Inbox=("Inbox", "sum"), Spam=("Spam", "sum")).reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=domain_df["Domain"], y=domain_df["Inbox"], name="Inbox", marker_color="#10b981"))
            fig.add_trace(go.Bar(
                x=domain_df["Domain"], y=domain_df["Spam"], name="Spam", marker_color="#ef4444"))
            fig.update_layout(barmode="group", title="Inbox vs Spam by Domain", margin=dict(
                t=40, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)

    # HISTORICAL VIEW
    else:
        results = load_placement_results(
            datetime.combine(start_date, datetime.min.time()),
            datetime.combine(end_date, datetime.max.time())
        )

        total_inbox = sum(1 for r in results if str(
            r.get("placement", "")).upper() == "INBOX")
        total_spam = sum(1 for r in results if str(
            r.get("placement", "")).upper() == "SPAM")
        total_all = total_inbox + total_spam

        m1, m2, m3, m4, m5 = st.columns(5)
        for col, label, value, sub, icon in [
            (m1, "Accounts", len(enabled_accounts), "Enabled mailboxes", "👥"),
            (m2, "Domains", len(enabled_domains), "Enabled domains", "🌐"),
            (m3, "Inbox", total_inbox, "Total INBOX", "📥"),
            (m4, "Spam", total_spam, "Total Spam", "🚫"),
            (m5, "All-mail", total_all, "Total All Mail", "📧"),
        ]:
            with col:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">{label} <span>{icon}</span></div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("### 📋 Placement Results (from Database)")
        if results:
            df_res = pd.DataFrame(results)
            cols = [c for c in ["date", "domain", "seed_email",
                                "placement", "inbox", "spam"] if c in df_res.columns]
            st.dataframe(
                df_res[cols], use_container_width=True, hide_index=True)
        else:
            st.info(f"No results found for {start_date} → {end_date}")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<div class="section-title">🚀 Run Placement Test</div>', unsafe_allow_html=True)

        if not enabled_accounts:
            st.warning("Please enable at least one mailbox (Accounts tab).")
        elif not enabled_domains:
            st.warning("Please enable at least one domain (Domains tab).")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                hours_back = st.number_input("Hours to look back", 1, 48, 3)
            with c2:
                max_workers = st.slider("Parallel workers", 1, 12, 8)
            with c3:
                save_to_mongo = st.checkbox(
                    "Save results to MongoDB", value=True)

            if st.button("Start Inbox Placement Test", type="primary", use_container_width=True):
                st.info(
                    f"Checking {len(enabled_accounts)} mailboxes against {len(enabled_domains)} domains...")
                with st.spinner("Scanning..."):
                    results_live, errors = check_all_mailboxes(
                        accounts=enabled_accounts,
                        domains=enabled_domains,
                        hours_back=hours_back,
                        max_workers=max_workers
                    )
                if not results_live:
                    st.error("No results returned")
                    st.stop()

                st.session_state.live_df = pd.DataFrame(results_live)
                st.session_state.live_errors = errors
                st.session_state.show_live_results = True

                if save_to_mongo:
                    try:
                        collection = get_results_collection()
                        to_save = st.session_state.live_df[
                            st.session_state.live_df["Placement"] != "Not Received"
                        ].copy()
                        if not to_save.empty:
                            records = []
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            for _, row in to_save.iterrows():
                                records.append({
                                    "date": now,
                                    "domain": row["Domain"],
                                    "sender_email": "",
                                    "seed_email": row["Mailbox"],
                                    "placement": row["Placement"].upper(),
                                    "inbox": int(row["Inbox"]),
                                    "spam": int(row["Spam"])
                                })
                            collection.insert_many(records)
                            st.success(f"✅ Saved {len(records)} records")
                    except Exception as e:
                        st.error(f"MongoDB Error: {e}")
                st.rerun()

        st.markdown("---")
        st.markdown("### 📈 Visualization")
        if results:
            c1, c2 = st.columns(2)
            with c1:
                fig = px.pie(
                    pd.DataFrame({"Type": ["Inbox", "Spam"], "Count": [
                                 total_inbox, total_spam]}),
                    values="Count", names="Type", color="Type",
                    color_discrete_map={"Inbox": "#10b981", "Spam": "#ef4444"},
                    title="Overall Inbox vs Spam", hole=0.45
                )
                fig.update_traces(textposition='inside',
                                  textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                df_chart = pd.DataFrame(results)
                domain_df = df_chart.groupby("domain").agg(
                    Inbox=("placement", lambda x: (
                        x.str.upper() == "INBOX").sum()),
                    Spam=("placement", lambda x: (
                        x.str.upper() == "SPAM").sum())
                ).reset_index()
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=domain_df["domain"], y=domain_df["Inbox"], name="Inbox", marker_color="#10b981"))
                fig.add_trace(go.Bar(
                    x=domain_df["domain"], y=domain_df["Spam"], name="Spam", marker_color="#ef4444"))
                fig.update_layout(barmode="group", title="Inbox vs Spam by Domain", margin=dict(
                    t=40, b=20, l=20, r=20))
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for charts in the selected date range.")


# ============================================================
# PAGE: ACCOUNTS
# ============================================================
elif st.session_state.page == "Accounts":
    st.markdown('<div class="section-title">👥 Manage Mailboxes</div>',
                unsafe_allow_html=True)

    if accounts:
        rows = [{"No.": i, "Mailbox": a["email"],
                 "Type": "Gmail" if a["email"].endswith("@gmail.com") else "Google Workspace",
                 "Status": "✅ Enabled" if a.get("enabled", True) else "❌ Disabled"}
                for i, a in enumerate(accounts, 1)]
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True, hide_index=True)
    else:
        st.info("No mailboxes added yet.")

    st.markdown("### Enable / Disable Mailbox")
    if accounts:
        selected_email = st.selectbox(
            "Select mailbox", [a["email"] for a in accounts], key="acc_sel")
        current = next(a for a in accounts if a["email"] == selected_email)
        is_enabled = current.get("enabled", True)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Disable" if is_enabled else "Enable", type="primary", use_container_width=True):
                for a in accounts:
                    if a["email"] == selected_email:
                        a["enabled"] = not is_enabled
                        break
                st.session_state.accounts = accounts
                save_accounts(accounts)
                st.success(
                    f"{'Disabled' if is_enabled else 'Enabled'}: {selected_email}")
                st.rerun()
        with c2:
            if st.button("🗑️ Delete permanently", use_container_width=True):
                accounts = [a for a in accounts if a["email"]
                            != selected_email]
                st.session_state.accounts = accounts
                save_accounts(accounts)
                st.success(f"Deleted: {selected_email}")
                st.rerun()

    st.divider()
    with st.expander("➕ Add Mailbox"):
        with st.form("add_mailbox"):
            new_email = st.text_input("Email")
            new_password = st.text_input("App Password", type="password")
            if st.form_submit_button("Add Mailbox", type="primary"):
                if new_email and new_password:
                    clean_email = clean_email_address(new_email)
                    clean_pass = clean_app_password(new_password)
                    if any(a["email"] == clean_email for a in accounts):
                        st.warning("Mailbox already exists")
                    else:
                        accounts.append(
                            {"email": clean_email, "password": clean_pass, "enabled": True})
                        st.session_state.accounts = accounts
                        save_accounts(accounts)
                        st.success(f"Added: {clean_email}")
                        st.rerun()
                else:
                    st.error("Please fill both fields")


# ============================================================
# PAGE: DOMAINS
# ============================================================
elif st.session_state.page == "Domains":
    st.markdown('<div class="section-title">🌐 Manage Sender Domains</div>',
                unsafe_allow_html=True)

    # Clean domains
    cleaned = []
    for d in domains:
        name, enabled = None, True
        if isinstance(d, dict):
            name = d.get("domain") or d.get("name")
            enabled = d.get("enabled", True)
            if isinstance(name, dict):
                name = name.get("domain")
            elif isinstance(name, str) and name.strip().startswith("{"):
                try:
                    parsed = ast.literal_eval(name)
                    if isinstance(parsed, dict):
                        name = parsed.get("domain")
                        enabled = parsed.get("enabled", enabled)
                except:
                    pass
        elif isinstance(d, str):
            if d.strip().startswith("{"):
                try:
                    parsed = ast.literal_eval(d)
                    if isinstance(parsed, dict):
                        name = parsed.get("domain")
                        enabled = parsed.get("enabled", True)
                except:
                    name = d
            else:
                name = d
        else:
            name = str(d)

        if name:
            name = str(name).strip().lstrip("@").lower()
            cleaned.append({"domain": name, "enabled": bool(enabled)})

    seen = set()
    domains = []
    for item in cleaned:
        if item["domain"] not in seen:
            seen.add(item["domain"])
            domains.append(item)
    st.session_state.domains = domains
    save_domains(domains)

    # Date Filter
    st.markdown("##### 📅 Filter by Date")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])

    with c1:
        selected_date = st.date_input(
            "Date",
            value=st.session_state.get("dom_date", datetime.now().date()),
            key="dom_date"
        )

    with c2:
        range_option = st.selectbox(
            "Range",
            ["Today (1 day)", "Yesterday (1 day)", "Last 7 days", "Custom"],
            key="dom_range"
        )

    today = datetime.now().date()
    if range_option == "Today (1 day)":
        start_date = end_date = today
    elif range_option == "Yesterday (1 day)":
        start_date = end_date = today - timedelta(days=1)
    elif range_option == "Last 7 days":
        start_date, end_date = today - timedelta(days=6), today
    else:
        start_date = end_date = selected_date

    with c3:
        st.write("")
        if st.button("Apply", type="primary", use_container_width=True, key="dom_apply"):
            st.rerun()

    with c4:
        st.write("")
        if st.button("Today", use_container_width=True, key="dom_today"):
            st.session_state.dom_range = "Today (1 day)"
            st.session_state.dom_date = today
            st.rerun()

    # Load results - now uses LATEST only (no repeated counts)
    results = load_placement_results(
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date, datetime.max.time())
    )

    total_inbox = sum(1 for r in results if str(
        r.get("placement", "")).upper() == "INBOX")
    total_spam = sum(1 for r in results if str(
        r.get("placement", "")).upper() == "SPAM")
    total_all = total_inbox + total_spam
    enabled_count = sum(1 for d in domains if d.get("enabled", True))

    # KPI CARDS (current / latest counts only)
    m1, m2, m3, m4, m5 = st.columns(5)
    for col, label, value, sub, icon in [
        (m1, "Accounts", len(enabled_accounts), "Enabled mailboxes", "👥"),
        (m2, "Domains", enabled_count, "Enabled domains", "🌐"),
        (m3, "Inbox", total_inbox, "Total INBOX", "📥"),
        (m4, "Spam", total_spam, "Total Spam", "🚫"),
        (m5, "All-mail", total_all, "Total All Mail", "📧"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label} <span>{icon}</span></div>
                <div class="metric-value">{value}</div>
                <div class="metric-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # SEARCH BAR
    st.markdown("##### 🔍 Search Domain")
    search_query = st.text_input(
        "Search domain...",
        placeholder="Type domain name (e.g. example.com)",
        key="domain_search",
        label_visibility="collapsed"
    )

    if search_query:
        filtered_domains = [
            d for d in domains
            if search_query.lower() in d["domain"].lower()
        ]
    else:
        filtered_domains = domains

    st.caption(
        f"{enabled_count} of {len(domains)} enabled • Showing {len(filtered_domains)} domain(s) • {start_date} → {end_date}")

    if not domains:
        st.info("No domains added yet.")
    elif not filtered_domains:
        st.warning(f"No domain found matching *{search_query}*")
    else:
        h1, h2, h3, h4, h5, h6 = st.columns([3.2, 1.4, 1.4, 2.2, 1.4, 0.8])
        with h1:
            st.markdown("<div class='domain-header'>Domain</div>",
                        unsafe_allow_html=True)
        with h2:
            st.markdown("<div class='domain-header'>Inbox</div>",
                        unsafe_allow_html=True)
        with h3:
            st.markdown("<div class='domain-header'>Spam</div>",
                        unsafe_allow_html=True)
        with h4:
            st.markdown("<div class='domain-header'>Status</div>",
                        unsafe_allow_html=True)
        with h5:
            st.markdown("<div class='domain-header'>Total</div>",
                        unsafe_allow_html=True)
        with h6:
            st.markdown("<div class='domain-header'>Delete</div>",
                        unsafe_allow_html=True)

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        for idx, d in enumerate(filtered_domains):
            name = d["domain"]
            is_enabled = d.get("enabled", True)

            domain_results = [r for r in results if r.get("domain") == name]
            inbox_c = sum(1 for r in domain_results if str(
                r.get("placement", "")).upper() == "INBOX")
            spam_c = sum(1 for r in domain_results if str(
                r.get("placement", "")).upper() == "SPAM")
            total_c = inbox_c + spam_c

            c1, c2, c3, c4, c5, c6 = st.columns([3.2, 1.4, 1.4, 2.2, 1.4, 0.8])

            with c1:
                st.markdown(
                    f"<div style='font-weight:600; padding-top:12px; font-size:0.95rem;'>{name}</div>",
                    unsafe_allow_html=True
                )
            with c2:
                st.markdown(
                    f"""<div class="inbox-badge" style="margin-top:6px;">📥 {inbox_c}</div>""",
                    unsafe_allow_html=True
                )
            with c3:
                st.markdown(
                    f"""<div class="spam-badge" style="margin-top:6px;">🚫 {spam_c}</div>""",
                    unsafe_allow_html=True
                )
            with c4:
                original_idx = next((i for i, x in enumerate(
                    domains) if x["domain"] == name), idx)
                new_status = st.toggle(
                    "Enabled" if is_enabled else "Disabled",
                    value=is_enabled,
                    key=f"tog_{original_idx}_{name}"
                )
                if new_status != is_enabled:
                    domains[original_idx]["enabled"] = new_status
                    st.session_state.domains = domains
                    save_domains(domains)
                    st.rerun()
            with c5:
                st.markdown(
                    f"<div style='color:#6b7280; padding-top:12px; font-size:0.9rem;'>Total: {total_c}</div>",
                    unsafe_allow_html=True
                )
            with c6:
                if st.button("🗑️", key=f"del_{original_idx}_{name}", help=f"Delete {name}"):
                    domains = [x for x in domains if x["domain"] != name]
                    st.session_state.domains = domains
                    save_domains(domains)
                    st.success(f"Deleted: {name}")
                    st.rerun()

    st.divider()

    with st.expander("➕ Add Domain"):
        with st.form("add_domain"):
            new_domain = st.text_input("Domain (example.com)")
            if st.form_submit_button("Add Domain", type="primary"):
                if new_domain:
                    clean = new_domain.strip().lstrip("@").lower()
                    if clean in [x["domain"] for x in domains]:
                        st.warning("Domain already exists")
                    else:
                        domains.append({"domain": clean, "enabled": True})
                        st.session_state.domains = domains
                        save_domains(domains)
                        st.success(f"Added: {clean}")
                        st.rerun()
                else:
                    st.error("Please enter a domain")
