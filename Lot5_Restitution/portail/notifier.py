#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Restitution : LLM Analyst, SMS, WhatsApp (Lot 5)
============================================================
Convertit un incident structuré (issu de la corrélation SIEM ou des modèles IA) en :
  • une EXPLICATION en langage naturel (« LLM Analyst »), dans la langue de l'utilisateur ;
  • une NOTIFICATION SMS courte (alerte temps réel) ;
  • un RAPPORT WhatsApp hebdomadaire de synthèse.

Toutes les sorties existent en français ET en anglais — la langue est choisie par utilisateur.

LLM Analyst : deux modes
  • « template » (par défaut) — explications déterministes basées sur des modèles bilingues.
    Toujours disponible, rapide, sans hallucination ni coût. Sert aussi de FILET DE SÉCURITÉ
    lorsque le LLM est indisponible.
  • « llm » — délègue à un Mistral/Llama via une API compatible OpenAI (Ollama, vLLM…), si
    LLM_API_URL est configuré.
"""
import argparse, json, os, sys
from datetime import datetime, timedelta

LANGS = ("fr", "en")

# --------------------------------------------------------------------------- #
# Catalogue de traductions (clés stables, valeurs par langue)
# --------------------------------------------------------------------------- #
T = {
    # Types d'incident
    "type.Ransomware":            {"fr": "rançongiciel", "en": "ransomware"},
    "type.Anomalie réseau / C2":  {"fr": "anomalie réseau / C2", "en": "network anomaly / C2"},
    "type.Compromission probable":{"fr": "compromission probable", "en": "probable compromise"},
    "type.Fraude interne":        {"fr": "fraude interne", "en": "insider fraud"},
    "type.Exfiltration":          {"fr": "exfiltration de données", "en": "data exfiltration"},
    # Tactiques MITRE (libellés courts)
    "tac.Initial Access":         {"fr": "accès initial", "en": "initial access"},
    "tac.Execution":              {"fr": "exécution", "en": "execution"},
    "tac.Persistence":            {"fr": "persistance", "en": "persistence"},
    "tac.Collection":             {"fr": "collecte", "en": "collection"},
    "tac.Command and Control":    {"fr": "commande et contrôle", "en": "command and control"},
    "tac.Impact":                 {"fr": "impact", "en": "impact"},
    # Phrases
    "explain.intro":              {"fr": "Le système a détecté un incident de type « {type} » sur l'hôte {entity}.",
                                   "en": "The system detected an incident of type \"{type}\" on host {entity}."},
    "explain.chain":              {"fr": "L'incident reconstitue une chaîne d'attaque en {n} étapes ({tactics}), cartographiée sur MITRE ATT&CK ({mitre}).",
                                   "en": "The incident reconstructs a {n}-step attack chain ({tactics}), mapped to MITRE ATT&CK ({mitre})."},
    "explain.afterhours":         {"fr": "L'activité s'est déroulée en dehors des heures ouvrables, ce qui renforce le caractère suspect.",
                                   "en": "The activity took place outside business hours, which reinforces its suspicious nature."},
    "explain.risk":               {"fr": "Le score de risque atteint {risk}/100.",
                                   "en": "The risk score reaches {risk}/100."},
    "explain.action.ransom":      {"fr": "Le poste a été isolé du réseau et une capture mémoire a été réalisée pour enquête.",
                                   "en": "The host has been isolated from the network and a memory snapshot was taken for investigation."},
    "explain.action.fraud":       {"fr": "Le compte a été placé en file de gel, en attente de validation par le DSI.",
                                   "en": "The account has been queued for freezing, pending DSI approval."},
    "explain.action.c2":          {"fr": "L'adresse distante a été bloquée au pare-feu et le DSI a été notifié.",
                                   "en": "The remote address has been blocked at the firewall and the DSI has been notified."},
    "explain.signature":          {"fr": "— NEXUS Analyst", "en": "— NEXUS Analyst"},

    # SMS
    "sms.title":                  {"fr": "🚨 NEXUS SOC", "en": "🚨 NEXUS SOC"},
    "sms.body":                   {"fr": "{type} sur {entity} · risque {risk}/100. Action : {action}. Détails : {url}",
                                   "en": "{type} on {entity} · risk {risk}/100. Action: {action}. Details: {url}"},
    "sms.action.isolate":         {"fr": "isoler", "en": "isolate"},
    "sms.action.freeze":          {"fr": "geler le compte", "en": "freeze account"},
    "sms.action.block":           {"fr": "bloquer l'IP", "en": "block IP"},

    # Rapport hebdomadaire WhatsApp
    "wa.header":                  {"fr": "📊 *Rapport Sécurité NEXUS SOC — Semaine {week}*",
                                   "en": "📊 *NEXUS SOC Security Report — Week {week}*"},
    "wa.tenant":                  {"fr": "Organisation : *{tenant}*", "en": "Organization: *{tenant}*"},
    "wa.score":                   {"fr": "✅ Score de sécurité : *{score}/100* ({delta} vs semaine dernière)",
                                   "en": "✅ Security score: *{score}/100* ({delta} vs last week)"},
    "wa.week_label":              {"fr": "📈 *Cette semaine*", "en": "📈 *This week*"},
    "wa.line_blocked":            {"fr": "• {n} tentative{s_fr} bloquée{s_fr}", "en": "• {n} attempt{s_en} blocked"},
    "wa.line_phishing":            {"fr": "• {n} clic{s_fr} sur un lien suspect — email retiré automatiquement",
                                   "en": "• {n} click{s_en} on a suspicious link — email auto-removed"},
    "wa.line_updates":            {"fr": "• {n} poste{s_fr} avec mises à jour critiques en attente",
                                   "en": "• {n} host{s_en} with critical updates pending"},
    "wa.action_label":            {"fr": "⚠ *Action requise*", "en": "⚠ *Action required*"},
    "wa.action_text":             {"fr": "Mettre à jour Windows sur les postes signalés.",
                                   "en": "Update Windows on the flagged hosts."},
    "wa.tip_label":               {"fr": "💡 *Conseil de la semaine*", "en": "💡 *Tip of the week*"},
    "wa.tip_text":                {"fr": "Activez l'authentification à deux facteurs sur vos comptes Google Workspace.",
                                   "en": "Enable two-factor authentication on your Google Workspace accounts."},
    "wa.link_label":              {"fr": "Rapport complet : {url}", "en": "Full report: {url}"},
}


def tr(key, lang, **kw):
    val = T.get(key, {}).get(lang, key)
    return val.format(**kw) if kw else val


# --------------------------------------------------------------------------- #
# LLM Analyst — explication d'un incident en langue naturelle
# --------------------------------------------------------------------------- #
class LLMAnalyst:
    def __init__(self, mode="template"):
        self.mode = mode  # "template" ou "llm"

    def explain(self, incident, lang="fr"):
        if self.mode == "llm" and os.getenv("LLM_API_URL"):
            try:
                return self._explain_llm(incident, lang)
            except Exception as e:
                print(f"[LLM] échec, repli sur le mode template : {e}", file=sys.stderr)
        return self._explain_template(incident, lang)

    def _explain_template(self, inc, lang):
        type_label = tr(f"type.{inc['type']}", lang)
        tactics = ", ".join(tr(f"tac.{t}", lang) for t in inc.get("tactiques", []))
        mitre = ", ".join(inc.get("mitre", []))
        n = len(inc.get("chaine", []))
        parts = [tr("explain.intro", lang, type=type_label, entity=inc["entity"])]
        if n >= 2:
            parts.append(tr("explain.chain", lang, n=n, tactics=tactics, mitre=mitre))
        if inc.get("activite_hors_heures"):
            parts.append(tr("explain.afterhours", lang))
        parts.append(tr("explain.risk", lang, risk=inc.get("risque", inc.get("risk", 0))))
        if inc["type"] == "Ransomware":
            parts.append(tr("explain.action.ransom", lang))
        elif inc["type"] in ("Fraude interne", "Exfiltration"):
            parts.append(tr("explain.action.fraud", lang))
        elif inc["type"] == "Anomalie réseau / C2":
            parts.append(tr("explain.action.c2", lang))
        return " ".join(parts)

    def _explain_llm(self, inc, lang):
        """Appel d'un Mistral/Llama via API compatible OpenAI (Ollama, vLLM…)."""
        import urllib.request
        prompt_lang = "français" if lang == "fr" else "English"
        sys_msg = (f"Tu es un analyste SOC senior. Explique l'incident à un DSI non-technicien, "
                   f"en {prompt_lang}, en 3 à 5 phrases claires et factuelles. Pas de jargon inutile.")
        body = json.dumps({
            "model": os.getenv("LLM_MODEL", "mistral"),
            "messages": [{"role": "system", "content": sys_msg},
                         {"role": "user", "content": json.dumps(inc, ensure_ascii=False)}],
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(os.getenv("LLM_API_URL"), data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read())
        return res["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------------------- #
# Notification SMS (courte alerte temps réel)
# --------------------------------------------------------------------------- #
def build_sms(incident, lang="fr", url="nexussoc.cm/i/" + "abc123"):
    action_key = {"Ransomware": "sms.action.isolate", "Fraude interne": "sms.action.freeze",
                  "Exfiltration": "sms.action.freeze", "Anomalie réseau / C2": "sms.action.block"
                 }.get(incident["type"], "sms.action.block")
    body = tr("sms.body", lang,
              type=tr(f"type.{incident['type']}", lang).capitalize(),
              entity=incident["entity"],
              risk=incident.get("risque", incident.get("risk", 0)),
              action=tr(action_key, lang), url=url)
    return f"{tr('sms.title', lang)} — {body}"


def send_sms(text, to_number, provider=None):
    """Connecteur SMS. En démonstration : simulation. En production : Twilio ou
    passerelle SMS locale (Orange/MTN via opérateur, après accord)."""
    print(f"  📱 SMS → {to_number} : {text}")


# --------------------------------------------------------------------------- #
# Rapport WhatsApp hebdomadaire
# --------------------------------------------------------------------------- #
def build_whatsapp_weekly(stats, lang="fr"):
    s = lambda n: "" if abs(n) == 1 else "s"
    lines = [
        tr("wa.header", lang, week=stats["week"]),
        tr("wa.tenant", lang, tenant=stats["tenant"]),
        "",
        tr("wa.score", lang, score=stats["score"], delta=stats["score_delta"]),
        "",
        tr("wa.week_label", lang),
        tr("wa.line_blocked",  lang, n=stats["blocked"],         s_fr=s(stats["blocked"]),         s_en=s(stats["blocked"])),
        tr("wa.line_phishing", lang, n=stats["phishing_clicks"], s_fr=s(stats["phishing_clicks"]), s_en=s(stats["phishing_clicks"])),
        tr("wa.line_updates",  lang, n=stats["updates_pending"], s_fr=s(stats["updates_pending"]), s_en=s(stats["updates_pending"])),
        "",
        tr("wa.action_label", lang),
        tr("wa.action_text", lang),
        "",
        tr("wa.tip_label", lang),
        tr("wa.tip_text", lang),
        "",
        tr("wa.link_label", lang, url=stats["report_url"]),
    ]
    return "\n".join(lines)


def send_whatsapp(text, to_number):
    """Connecteur WhatsApp Business API. Démonstration : simulation. En production,
    les messages hors fenêtre de 24h doivent suivre un TEMPLATE APPROUVÉ PAR META
    (paramètres dynamiques uniquement)."""
    print(f"  💬 WhatsApp → {to_number} :")
    for line in text.split("\n"):
        print("     " + line)


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Restitution (Lot 5)")
    ap.add_argument("--incident", default="../pipeline/out_lot2/correlated_incidents.json",
                    help="incident JSON (sortie de la corrélation SIEM)")
    ap.add_argument("--out", default="./out_lot5")
    args = ap.parse_args(); os.makedirs(args.out, exist_ok=True)

    inc = json.load(open(args.incident))[0]
    analyst = LLMAnalyst(mode="template")

    # Statistiques hebdomadaires simulées
    today = datetime.now()
    stats = {"week": today.isocalendar()[1], "tenant": "Ministère des Finances",
             "score": 72, "score_delta": "-8", "blocked": 14, "phishing_clicks": 1,
             "updates_pending": 2, "report_url": "nexussoc.cm/rapport/semaine"}

    print("NEXUS SOC — Restitution bilingue (FR / EN)\n" + "=" * 46)
    for lang in LANGS:
        print(f"\n────── {lang.upper()} ──────\n")
        explanation = analyst.explain(inc, lang)
        sms = build_sms(inc, lang)
        wa = build_whatsapp_weekly(stats, lang)

        print(f"[Analyst {lang}] {explanation}\n")
        send_sms(sms, "+237 6XX XX XX XX")
        print()
        send_whatsapp(wa, "+237 6XX XX XX XX")

        # Écriture des échantillons
        with open(f"{args.out}/explanation_{lang}.txt", "w") as f: f.write(explanation + "\n")
        with open(f"{args.out}/sms_{lang}.txt", "w") as f: f.write(sms + "\n")
        with open(f"{args.out}/whatsapp_{lang}.txt", "w") as f: f.write(wa + "\n")

    print(f"\nÉchantillons écrits dans {args.out}/")


if __name__ == "__main__":
    main()
