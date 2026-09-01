import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from pymongo import MongoClient

from email_checker import (
    clean_email_address,
    clean_app_password,
    check_all_mailboxes
)

load_dotenv()

# ============================================================
# MONGODB CONNECTION
# ============================================================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "inbox_test"

def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]

def load_accounts():
    return list(get_db()["accounts"].find({}, {"_id": 0}))

def save_accounts(accounts):
    db = get_db()
    db["accounts"].delete_many({})
    if accounts:
        db["accounts"].insert_many(accounts)

def load_domains():
    docs = list(get_db()["domains"].find({}, {"_id": 0}))
    return [d["domain"] for d in docs]

def save_domains(domains):
    db = get_db()
    db["domains"].delete_many({})
    if domains:
        db["domains"].insert_many([{"domain": d} for d in domains])

def get_results_collection():
    return get_db()["placement_results"]


st.set_page_config(page_title="Inbox Placement Tester", page_icon="📧", layout="wide")
st.title("📧 Inbox Placement Tester")
st.caption("Manage Mailboxes + Domains from Database")

# ============================================================
# LOAD DATA FROM DATABASE
# ============================================================
if "accounts" not in st.session_state:
    st.session_state.accounts = load_accounts()

if "domains" not in st.session_state:
    st.session_state.domains = load_domains()

accounts = st.session_state.accounts
domains = st.session_state.domains

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("Configuration")
st.sidebar.metric("Mailboxes", len(accounts))
st.sidebar.metric("Domains", len(domains))

# ============================================================
# 1. MANAGE MAILBOXES
# ============================================================
st.header("📬 Manage Mailboxes")

if accounts:
    df_acc = pd.DataFrame([
        {
            "No.": i,
            "Mailbox": a["email"],
            "Type": "Gmail" if a["email"].endswith("@gmail.com") else "Google Workspace"
        }
        for i, a in enumerate(accounts, 1)
    ])
    st.dataframe(df_acc, use_container_width=True, hide_index=True)
else:
    st.info("No mailboxes added yet.")

col1, col2 = st.columns(2)

with col1:
    with st.expander("➕ Add Mailbox"):
        with st.form("add_mailbox"):
            new_email = st.text_input("Email")
            new_password = st.text_input("App Password", type="password")
            if st.form_submit_button("Add Mailbox"):
                if new_email and new_password:
                    clean_email = clean_email_address(new_email)
                    clean_pass = clean_app_password(new_password)

                    if any(a["email"] == clean_email for a in accounts):
                        st.warning("Mailbox already exists")
                    else:
                        accounts.append({"email": clean_email, "password": clean_pass})
                        st.session_state.accounts = accounts
                        save_accounts(accounts)
                        st.success(f"Added: {clean_email}")
                        st.rerun()
                else:
                    st.error("Please fill both fields")

with col2:
    if accounts:
        with st.expander("🗑️ Remove Mailbox"):
            to_remove = st.selectbox("Select mailbox", [a["email"] for a in accounts])
            if st.button("Remove Mailbox"):
                accounts = [a for a in accounts if a["email"] != to_remove]
                st.session_state.accounts = accounts
                save_accounts(accounts)
                st.success(f"Removed: {to_remove}")
                st.rerun()

st.divider()

# ============================================================
# 2. MANAGE SENDER DOMAINS
# ============================================================
st.header("🌐 Manage Sender Domains")

if domains:
    st.dataframe(pd.DataFrame({"Domain": domains}), use_container_width=True, hide_index=True)
else:
    st.info("No domains added yet.")

col1, col2 = st.columns(2)

with col1:
    with st.expander("➕ Add Domain"):
        with st.form("add_domain"):
            new_domain = st.text_input("Domain (example.com)")
            if st.form_submit_button("Add Domain"):
                if new_domain:
                    d = new_domain.strip().lstrip("@").lower()
                    if d in domains:
                        st.warning("Domain already exists")
                    else:
                        domains.append(d)
                        st.session_state.domains = domains
                        save_domains(domains)
                        st.success(f"Added: {d}")
                        st.rerun()
                else:
                    st.error("Please enter a domain")

with col2:
    if domains:
        with st.expander("🗑️ Remove Domain"):
            to_remove = st.selectbox("Select domain", domains)
            if st.button("Remove Domain"):
                domains = [d for d in domains if d != to_remove]
                st.session_state.domains = domains
                save_domains(domains)
                st.success(f"Removed: {to_remove}")
                st.rerun()

st.divider()

# ============================================================
# 3. RUN TEST
# ============================================================
st.header("🚀 Run Placement Test")

if not accounts:
    st.warning("Please add at least one mailbox")
elif not domains:
    st.warning("Please add at least one domain")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        hours_back = st.number_input("Hours to look back", 1, 48, 3)
    with col2:
        max_workers = st.slider("Parallel workers", 1, 12, 8)
    with col3:
        save_to_mongo = st.checkbox("Save results to MongoDB", value=True)

    if st.button("Start Inbox Placement Test", type="primary", use_container_width=True):

        st.info(f"Checking {len(accounts)} mailboxes against {len(domains)} domains...")

        with st.spinner("Scanning..."):
            results, errors = check_all_mailboxes(
                accounts=accounts,
                domains=domains,
                hours_back=hours_back,
                max_workers=max_workers
            )

        if errors:
            st.warning(f"{len(errors)} mailbox(es) failed")
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

        if not results:
            st.error("No results returned")
            st.stop()

        df = pd.DataFrame(results)

        # Overall
        st.subheader("📊 Overall Results")
        mailbox_level = df.groupby("Mailbox").agg(Inbox=("Inbox", "max"), Spam=("Spam", "max")).reset_index()
        total_inbox = int(mailbox_level["Inbox"].sum())
        total_spam = int(mailbox_level["Spam"].sum())
        total_received = min(total_inbox + total_spam, len(accounts))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mailboxes", len(accounts))
        c2.metric("Total Inbox", total_inbox)
        c3.metric("Total Spam", total_spam)
        c4.metric("Total Received", total_received)

        # Domain Summary
        st.subheader("🌐 Domain Summary")
        domain_summary = df.groupby("Domain").agg(Inbox=("Inbox", "sum"), Spam=("Spam", "sum")).reset_index()
        domain_summary["Total"] = len(accounts)
        domain_summary["Inbox %"] = (domain_summary["Inbox"] / len(accounts) * 100).round(2)
        domain_summary["Spam %"] = (domain_summary["Spam"] / len(accounts) * 100).round(2)
        domain_summary = domain_summary[["Domain", "Inbox", "Spam", "Total", "Inbox %", "Spam %"]]
        st.dataframe(domain_summary, use_container_width=True, hide_index=True)

        # Detailed
        st.subheader("📋 Detailed Results")
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Save results
        if save_to_mongo:
            try:
                collection = get_results_collection()
                to_save = df[df["Placement"] != "Not Received"].copy()

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
                    result = collection.insert_many(records)
                    st.success(f"✅ Saved {len(result.inserted_ids)} records to database")
                else:
                    st.warning("No valid results to save")
            except Exception as e:
                st.error(f"MongoDB Error: {e}")

                
