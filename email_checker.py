import imaplib
import email
from email.utils import parseaddr
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
import re


def clean_email_address(email_addr: str) -> str:
    return email_addr.strip().lower() if email_addr else ""


def clean_app_password(password: str) -> str:
    return password.replace(" ", "").strip() if password else ""


def _get_sender_domain(msg) -> str:
    from_header = msg.get("From", "")
    _, addr = parseaddr(from_header)
    addr = (addr or "").lower().strip()
    if "@" in addr:
        return addr.split("@")[-1]
    return ""


def _parse_internaldate(internaldate_str: str):
    try:
        return datetime.strptime(internaldate_str.strip('"'), "%d-%b-%Y %H:%M:%S %z")
    except Exception:
        return None


def check_mailbox(account: Dict, domains: List[str], hours_back: int = 3) -> Tuple[List[Dict], str]:
    email_addr = account["email"]
    password = account["password"]
    results = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(email_addr, password)
    except Exception as e:
        return [], f"Login failed: {str(e)}"

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    since_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")

    folders = [
        ("INBOX", "Inbox"),
        ("[Gmail]/Spam", "Spam"),
    ]

    domain_counts = {d: {"Inbox": 0, "Spam": 0} for d in domains}

    try:
        for folder_name, placement in folders:
            try:
                status, _ = mail.select(folder_name, readonly=True)
                if status != "OK":
                    continue
            except Exception:
                continue

            for domain in domains:
                try:
                    # Faster search
                    status, data = mail.search(None, f'(SINCE {since_date} FROM "@{domain}")')
                    if status != "OK" or not data or not data[0]:
                        continue

                    msg_ids = data[0].split()

                    # Only check the latest 15 emails (big speed boost)
                    msg_ids = msg_ids[-15:]

                except Exception:
                    continue

                found = False
                for msg_id in reversed(msg_ids):  # start from newest
                    try:
                        status, msg_data = mail.fetch(msg_id, "(RFC822.HEADER INTERNALDATE)")
                        if status != "OK" or not msg_data:
                            continue

                        raw_header = None
                        internaldate = None

                        for part in msg_data:
                            if isinstance(part, tuple):
                                raw_header = part[1]
                            elif isinstance(part, bytes) and b"INTERNALDATE" in part:
                                match = re.search(rb'INTERNALDATE "([^"]+)"', part)
                                if match:
                                    internaldate = match.group(1).decode()

                        if not raw_header or not internaldate:
                            continue

                        msg = email.message_from_bytes(raw_header)
                        msg_dt = _parse_internaldate(internaldate)

                        if not msg_dt:
                            continue
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)

                        if _get_sender_domain(msg) == domain and msg_dt >= cutoff:
                            found = True
                            break
                    except Exception:
                        continue

                if found:
                    domain_counts[domain][placement] = 1

        for domain, counts in domain_counts.items():
            inbox = counts["Inbox"]
            spam = counts["Spam"]
            total = inbox + spam

            if total == 0:
                placement = "Not Received"
            elif spam == 0:
                placement = "Inbox"
            elif inbox == 0:
                placement = "Spam"
            else:
                placement = "Mixed"

            results.append({
                "Mailbox": email_addr,
                "Domain": domain,
                "Inbox": inbox,
                "Spam": spam,
                "Total": total,
                "Placement": placement
            })

        mail.logout()
        return results, None

    except Exception as e:
        try:
            mail.logout()
        except:
            pass
        return [], str(e)


def check_all_mailboxes(accounts: List[Dict], domains: List[str], hours_back: int = 3, max_workers: int = 8):
    all_results = []
    errors = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(check_mailbox, acc, domains, hours_back): acc
            for acc in accounts
        }

        for future in as_completed(futures):
            acc = futures[future]
            try:
                results, error = future.result()
                if error:
                    errors.append({"Mailbox": acc["email"], "Error": error})
                else:
                    all_results.extend(results)
            except Exception as e:
                errors.append({"Mailbox": acc["email"], "Error": str(e)})

    return all_results, errors

