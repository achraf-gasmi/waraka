# WARAKA_CONTEXT.md — Full Project Intelligence
# Everything Claude Code needs to understand WHY this project exists,
# WHO it serves, WHAT regulations it must respect, and HOW the domain works.
# Read this alongside CLAUDE.md and WARAKA_SPEC.md.

---

## 1. What this project is and why it exists

Waraka (وَرَقَة — Arabic for "document" or "case file") is an AI compliance
platform built specifically for the Tunisian financial sector. It is not a
generic RegTech tool adapted for Tunisia — it is built from the ground up
for Tunisian regulations, in French and Arabic, for Tunisian banks.

### The burning problem

On December 22, 2025, the Banque Centrale de Tunisie (BCT) published
circulaire n°2025-17, which mandates that all banks immediately file
Suspicious Transaction Reports (STRs) via the goAML platform operated by
CTAF (Commission Tunisienne des Analyses Financières). Banks must also:
- Transmit a quarterly report of frozen assets within 20 working days
- Notify BCT within 5 days of any CTAF correspondent designation
- Maintain a formal documented risk assessment updated every 3 years
- Integrate AML/CFT rules into their code of ethics

Most Tunisian banks have no automated tooling for any of this. Compliance
officers are drafting STRs manually in Word documents.

### The volume crisis

- 2022: CTAF received 529 STRs
- 2023: CTAF received 804 STRs (+52% in one year)
- 93.28% of all STRs come from banks and the National Post Office
- CTAF is chronically understaffed relative to this volume
- A FATF technical mission visited BCT and CTAF in June 2025 and raised
  serious concerns about Tunisia's compliance posture

### The FATF risk

Tunisia was on the FATF grey list from 2017 to 2019. Going back on the
grey list would mean:
- Correspondent banking relationships threatened
- Foreign investment freezes
- International transactions harder for all Tunisian banks
- National economic credibility damaged

BCT circulaire 2025-17 is a direct response to FATF pressure. The urgency
is real and institutional.

---

## 2. The regulatory framework — what Waraka must serve

### Master law: Loi organique n°2015-26 (August 2015) modified by 2019-9

This is Tunisia's primary AML/CFT law. Key articles:

**Article 107** — Lists all entities required to report suspicious
transactions to CTAF:
1. Credit institutions (banks)
2. Microfinance institutions
3. National Post Office (ONP)
4. Stock exchange intermediaries
5. Currency exchange bureaus
6. Insurance companies
7. Real estate agents
8. Notaries, lawyers, accountants (for certain transactions)
9. Casino operators
10. Dealers in precious metals and stones

Waraka v1 targets #1 (banks). v2 expansion targets #2, #3, #5.

**Article 118** — Creates CTAF as Tunisia's Financial Intelligence Unit (FIU).
CTAF receives, analyzes, and transmits STRs to the prosecutor when
suspicion is confirmed.

**PEP definition (Article 2 modified by 2019-9):**
Politically Exposed Persons include those who exercise or have exercised
important public functions in Tunisia or abroad — including:
- President of the Republic
- Head of government
- Senior politicians
- Legislative and local elected officials
- Senior officials of public authorities and constitutional bodies
- Senior judges and military officers
- Directors of public institutions
- Senior party officials
- Their immediate family members and close associates

This definition must be implemented in the entity screening logic.

### BCT circulaires — the operational layer

BCT issues circulaires (binding instructions to banks) continuously.
In 2024 alone: 14 circulaires + 23 notes.
In 2023: 8 circulaires + 24 notes.

Key circulaires relevant to Waraka:

- **n°2025-17 (Dec 22, 2025)** — LBC/FT reform. Mandates goAML filing,
  quarterly frozen assets reporting, 3-year risk assessment cycle. This is
  the primary regulatory driver for Waraka v1.

- **n°2017-08** — Internal control framework for AML/CFT. Circulaire
  2025-17 amends this. Banks must understand how 2025-17 changes 2017-08.

- **n°2019-01** — BCT fintech sandbox rules. Relevant for obtaining
  regulatory approval to pilot Waraka with a bank.

- **n°2024-07** — Reporting of foreign transfers to associations/NGOs.
  Extended monitoring requirements.

Circulaires are published as PDFs at bct.gov.tn. The regulatory monitor
agent (v2) will index these.

### CMF (Conseil du Marché Financier)

In January 2025, CMF created a dedicated AML/CFT entity. CMF supervises
stock exchange intermediaries — also Article 107 obligated entities.
Potential expansion market for Waraka.

### goAML — the technical filing platform

goAML is a UNODC-developed platform used by 70+ countries as their FIU
reporting system. Tunisia's CTAF uses goAML for STR reception.

Reports are submitted as XML files following the UNODC goAML schema.
Report types relevant to Waraka:
- **STR-T** (Suspicious Transaction Report — Transaction): used when the
  transaction has already occurred. This is the primary type for v1.
- **STR-A** (Suspicious Transaction Report — Attempt): used when the
  transaction was attempted but blocked.
- **AIF** (Additional Information File): follow-up to a previously filed STR.

The XML schema is available from UNODC. Key fields:
- rentity_id: reporting entity identifier
- report_code: STR
- submission_code: E (Electronic)
- entity_reference: bank's internal case reference
- transaction details: date, amount, currency, sender, receiver
- narrative: free-text French description of the suspicious activity

Data quality is CTAF's biggest operational problem. Banks submit incomplete
or poorly structured STRs. Waraka's core value is producing high-quality,
complete, consistently formatted STRs.

---

## 3. The market — who pays and why

### 23 Tunisian banks — all obligated, all underserved

Top banks by employee count (2025 data):
- BIAT (Banque Internationale Arabe de Tunisie): 1,998 employees
- Attijari Bank: 1,119 employees
- Banque Zitouna: 762 employees
- Amen Bank: 660 employees
- Banque de Tunisie: 548 employees
- UIB (Union Internationale de Banques): 535 employees
- STB (Société Tunisienne de Banque): 436 employees
- BH Bank (Achraf's employer): TND 499M market cap

All 23 banks are subject to BCT circulaire 2025-17. All must file via
goAML. None have AI-powered STR drafting tools.

### The fintech pipeline

Tunisia's fintech sector raised TND 150M in 2024, growing 15% annually.
Key players:
- **Flouci** (by Kaoun): 250,000+ active accounts, eKYC via national ID,
  recognized in Forbes Middle East Fintech 50 (2025). Needs AML compliance
  infrastructure as it scales.
- **EasyBank**: raised TND 1.2M in 2025, expanding to MENA and France.
- **Dabchy Pay**: payment gateway for e-commerce.
- **E-Dinar**: mobile wallet for underbanked communities.

64% of Tunisian adults are financially excluded or underserved. Every
fintech serving them needs KYC/AML compliance. None have the resources
to build it internally.

### KYB obligations for businesses

Under Article 107 of loi 2015-26, fintechs processing payments must:
1. Verify customer identities using official documents
2. Identify Ultimate Beneficial Owners (UBOs — individuals owning 25%+)
3. Cross-check against UNSC and OFAC sanctions lists
4. Screen for Politically Exposed Persons (PEPs)
5. File STRs with CTAF within 10 business days of detecting suspicious activity
6. Collect trade licenses from the Tunisian Commercial Register (RNE)

This creates a second product tier for Waraka targeting fintechs.

---

## 4. Competitive landscape — why no one has done this for Tunisia

### Global tools (not calibrated for Tunisia)
- **ComplyAdvantage**: built for EU/UK markets, priced in GBP
- **Mozn (FOCAL)**: Saudi-focused, reduces false positives by 67% but
  not calibrated for BCT regulatory text
- **AML Watcher**: opened Dubai office in January 2025, focused on GCC
- **Sumsub**: global KYC platform, not CTAF-goAML integrated

### Three structural gaps in all existing tools for Tunisia:
1. **Arabic name transliteration fails**: "Mohamed" vs "Muhammad" vs
   "محمد" — existing tools miss matches. Tunisian names have specific
   romanization patterns that differ from Gulf Arabic.
2. **BCT circular coverage is zero**: No tool monitors BCT circulaires,
   notes, and instructions in French and maps them to policy gaps.
3. **goAML XML generation is manual**: No tool produces ready-to-submit
   goAML XML from natural language input.

Waraka addresses all three. There is no direct competitor in Tunisia.

---

## 5. Technology decisions and why

### Why LangGraph (not CrewAI, not AutoGen)

LangGraph 1.0 (released October 2025) is the only framework that natively
supports human-in-the-loop (HITL) workflows — pausing execution, saving
state, waiting for analyst approval, then resuming. This is non-negotiable
for a compliance tool. Regulators require human oversight on every AI
decision. LangGraph builds this in natively.

Production proof: JP Morgan, BlackRock, Klarna, Uber all run LangGraph
in production. 90M monthly downloads.

### Why GraphRAG for v2 (regulatory monitor)

BCT circulaires cross-reference each other constantly. Circulaire 2025-17
modifies circulaire 2017-08 which references circulaire 2006-19 and
circulaire 2021-05. A flat vector database (plain ChromaDB) cannot capture
these cross-references. A knowledge graph can. When BCT issues a new
circulaire, GraphRAG traverses the reference graph to find all affected
policies — flat RAG cannot do this.

Use plain ChromaDB for v1 (STR agent doesn't need cross-document reasoning).
Use GraphRAG for v2 (regulatory monitor needs it).

### Why XGBoost + SHAP for AML scoring (not deep learning)

Regulators require explainable decisions. When a compliance officer asks
"why was this transaction flagged?", the answer cannot be "the neural
network said so." SHAP values produce feature-level explanations:
"This transaction was flagged primarily because: (1) the destination
jurisdiction is on the FATF high-risk list (+0.34), (2) there are 2+
intermediary entities (+0.28), (3) no prior business relationship (+0.19)."
A compliance officer can put this in a CTAF report. A deep learning
explanation cannot be put in a report.

Research validation: XGBoost achieves 97.5% AUC on AML detection tasks.
SHAP values allowed compliance teams to understand individual feature
contributions in published research (2025).

### Why CAMeL Tools + MARBERTV2 for Arabic NLP

CAMeL Tools is the leading open-source Arabic NLP toolkit — dialect ID,
morphological analysis, NER. MARBERTV2 was the top-performing model on
AraFinNLP 2024, the first Arabic Financial NLP shared task, which
specifically included Tunisian dialect banking queries. This is the only
model fine-tuned on Tunisian financial Arabic — not just MSA (Modern
Standard Arabic) or Gulf dialect.

### Why Claude Sonnet 4.6 (not GPT-4o, not Llama)

- Temperature 0.0 produces deterministic outputs — critical for compliance
  where the same input must produce consistent analysis
- 1M token context window at standard price ($3/$15 per MTok input/output)
- Prompt caching saves up to 90% on repeated system prompts (compliance
  tools reuse long system prompts constantly)
- Multilingual: strong French + Arabic + English in one model
- Anthropic's safety design aligns with compliance use cases

### Why on-premise Docker for data layer (not cloud)

Tunisian banks have strict data residency requirements. Transaction data
and STR drafts cannot leave Tunisia or go to foreign cloud providers
without BCT approval. Running PostgreSQL + ChromaDB locally in Docker
satisfies data residency while keeping the LLM calls to the Claude API
(which processes prompts, not stored customer data).

---

## 6. Public data sources — free, usable, referenced

### AML training data
- **IBM AMLSim**: github.com/IBM/AMLSim — synthetic banking transactions
  with labeled laundering patterns. Apache-2.0 license. Use for training
  the XGBoost risk scorer in v1.1.
- **NeurIPS 2023 AML dataset**: 176M+ synthetic transactions on Kaggle,
  calibrated to match real transaction distributions. Best open AML dataset
  available.

### Sanctions data
- **OpenSanctions**: opensanctions.org — 328 global sources including OFAC
  SDN, UN Security Council, EU sanctions. Free for non-commercial use.
  JSON/CSV daily delta updates. This is the sanctions_tool.py data source.
- **OFAC SDN list**: ofac.treasury.gov/sanctions-list-service — direct
  download in XML/CSV. Updated continuously. Free.
- **UN Security Council consolidated list**: available at un.org. Free.
  BCT requires Tunisian banks to screen against this list.

### Regulatory text
- **BCT circulaires**: bct.gov.tn — all circulaires as PDFs. Free.
- **CTAF activity reports**: ctaf.gov.tn — annual reports with STR
  typologies, sector data, and risk patterns. Free. Use for demo scenarios.
- **MENAFATF mutual evaluation reports**: menafatf.org — Tunisia's
  evaluation reports listing specific compliance deficiencies. Free.
- **AMEF consulting retrospectives**: amef-consulting.com — annual analysis
  of BCT circulaires in structured format. Free to read.

### Arabic NLP
- **AraFinNLP 2024 dataset**: aclanthology.org — Tunisian dialect banking
  queries with intent labels. Free.
- **CAMeL Tools**: github.com/CAMeL-Lab/camel_tools — MIT license.

---

## 7. The goAML challenge in detail

### Why STR quality matters so much

UNODC has explicitly stated that regulators (CTAF) are not responsible for
data quality in goAML submissions. The burden falls entirely on reporting
institutions (banks). Poor quality STRs:
- Get rejected and returned for correction (delay + rework)
- Cannot be analyzed by CTAF analysts
- Expose the bank to regulatory sanctions for incomplete reporting
- Undermine Tunisia's FATF compliance posture

Common STR quality problems Waraka must solve:
1. Missing entity identifiers (CIN, passport, company registration)
2. Incomplete transaction chains (missing intermediaries)
3. Vague narrative that doesn't explain why the transaction is suspicious
4. Wrong XML structure (fields in wrong order, missing required elements)
5. Currency and amount format errors
6. Date format inconsistencies

### The STR lifecycle

1. Transaction occurs (or is attempted)
2. Compliance system flags it (rule-based alert or analyst observation)
3. Analyst investigates: reviews account history, contacts client, checks
   sanctions lists, assesses risk
4. **Analyst drafts STR narrative** ← This is where Waraka intervenes
5. STR reviewed by compliance manager
6. STR submitted via goAML
7. CTAF receives, analyzes, and either archives or transmits to prosecutor

Waraka intervenes at step 4. It doesn't replace the analyst — it drafts
the STR narrative and XML from the analyst's plain-language description,
which the analyst then reviews, corrects if needed, and approves.

### The HITL (Human-in-the-Loop) requirement

BCT circulaire 2025-17 and the EU AI Act (August 2026) both require human
oversight on AI decisions in compliance contexts. Waraka's analyst approval
flow (approve / correct / submit) is not a feature — it is a legal
requirement. Every STR must have a human analyst who reviewed and approved
it before submission to CTAF.

LangGraph's native HITL support handles this: execution pauses after
generating the draft, saves state, waits for analyst action, then resumes
(or closes). The approval record is stored in war_corrections table and
constitutes the audit trail.

---

## 8. Startup path — legal and funding context

### Startup Act (Tunisia, 2018)

Tunisia's Startup Act (Décret gouvernemental n°2018-840) provides:
- **Label Startup**: merit-based label granting access to all benefits
- **Zero corporate tax**: labeled startups exempt from IS
- **State salary coverage**: employer + employee social charges covered
  by state (significant cost reduction)
- **Foreign currency account**: can hold and freely use foreign currency
- **AIR grant**: funding for proof of concept development (living
  expenses TND 1,000–5,000/month for one year)
- **AIR² grant**: support after seed round, toward Series A

Apply at startup.gov.tn. Decision in 30 days (or 3 days if already backed
by a recognized investment fund).

### BCT regulatory sandbox

BCT launched its fintech regulatory sandbox in January 2020. Governed by
BCT circular 2019-01. Allows fintechs to test innovative solutions with
real customers under BCT supervision. This is the formal channel for
piloting Waraka with a bank under regulatory oversight. A successful
sandbox pilot converts directly into a reference case study.

### Go-to-market sequence

1. Get Startup Act label → zero tax, state salary coverage
2. Apply to BCT sandbox → formal pilot authorization
3. First pilot: mid-size bank (BH Bank, Amen Bank, or Banque Zitouna)
   or fast-growing fintech (Flouci, EasyBank)
4. Pitch anchor: "BCT circulaire 2025-17 mandates goAML filing immediately.
   You have no tool. We do."
5. Post-pilot case study → expand to other Tunisian banks
6. Series A → expand to Francophone Africa (Morocco, Senegal, Ivory Coast)
7. European expansion → French/Luxembourg banks with MENA exposure

---

## 9. The demo scenario — always use this for testing

**Entity**: Société Immobilière Carthage SARL
**Registration**: RC B123456789, Tunis
**Transaction date**: March 15, 2026
**Amount**: TND 850,000
**Destination**: Gulf Properties FZE, Abu Dhabi, UAE
**Intermediary 1**: Mediterranean Holdings Ltd, Malta
**Intermediary 2**: Atlantic Capital SA, Luxembourg
**Justification given**: Real estate investment
**Documentation provided**: None
**Prior relationship**: None in system

**French input for the UI**:
"Notre client, la société Immobilière Carthage SARL (RC: B123456789, Tunis),
a effectué le 15 mars 2026 un virement de 850 000 TND vers une société
dénommée Gulf Properties FZE, domiciliée aux Émirats Arabes Unis (Abu Dhabi),
via deux sociétés intermédiaires : Mediterranean Holdings Ltd (Malte) et
Atlantic Capital SA (Luxembourg). Le client invoque un investissement
immobilier mais n'a fourni aucun contrat ni justificatif économique.
Aucune relation commerciale antérieure n'existe avec les bénéficiaires
dans nos systèmes. Le profil risque du client est classé moyen depuis
son ouverture de compte en 2019."

**Expected Waraka output**:
- Risk level: CRITICAL
- Confidence: 0.85–0.92
- Risk indicators detected:
  1. Transaction vers une juridiction à haut risque (UAE — FATF monitored)
  2. Recours à plusieurs intermédiaires sans justification commerciale (2)
  3. Absence de relation commerciale antérieure avec les bénéficiaires
  4. Montant élevé non habituel (TND 850,000)
  5. Absence de documentation justificative
- Entities: 4 (Carthage SARL, Gulf Properties FZE, Mediterranean Holdings,
  Atlantic Capital)
- Narrative: formal French compliance text, 350–450 words
- XML: valid goAML STR-T structure

---

## 10. What v2 and v3 add (do not build in v1)

**v2 — BCT Circular Monitor Agent**:
- Ingests new BCT circulaires as they are published (scrape bct.gov.tn)
- Chunks and indexes into ChromaDB + Neo4j knowledge graph
- Diffs new circulaire against bank's internal policy documents
- Identifies gaps and generates a prioritized action list
- Sends alerts to compliance manager

**v3 — Entity Screening Agent**:
- Arabic name disambiguation with transliteration handling
- Screens against OFAC SDN, UN consolidated list, EU sanctions
- PEP detection against Tunisian political database
- Cross-references Tunisian commercial register (RNE) for UBO chains
- Produces entity risk profile with confidence score

Do not mention v2 or v3 in v1 code. v1 is self-contained.

---

## 11. Key contacts and URLs for the project

| Resource | URL |
|---|---|
| CTAF (Tunisia FIU) | ctaf.gov.tn |
| BCT circulaires | bct.gov.tn |
| goAML (UNODC) | unodc.org/unodc/en/global-it-products/goaml.html |
| OpenSanctions | opensanctions.org |
| OFAC SDN list | ofac.treasury.gov/sanctions-list-service |
| Startup Act | startup.gov.tn |
| MENAFATF | menafatf.org |
| AraFinNLP dataset | aclanthology.org/2024.arabicnlp-1.34 |
| CAMeL Tools | github.com/CAMeL-Lab/camel_tools |
| IBM AMLSim | github.com/IBM/AMLSim |
| BCT regulatory retrospective | amef-consulting.com |
| Loi 2015-26 text | legislation-securite.tn |

---

*This document synthesizes research conducted April 2026.*
*Owner: Achraf Gasmi. Do not share externally.*
