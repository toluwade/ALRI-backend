"""FAQ data used by the support router and the AI support chat context."""

SUPPORT_FAQ: list[dict[str, str]] = [
    # ── General ───────────────────────────────────────────
    {
        "category": "general",
        "question": "What is ALRI?",
        "answer": (
            "ALRI is an AI-powered tool that interprets your lab results in plain "
            "language. Upload a PDF, image, or type your values manually and get "
            "instant, easy-to-understand explanations of your biomarkers."
        ),
    },
    {
        "category": "general",
        "question": "Is ALRI a substitute for medical advice?",
        "answer": (
            "No. ALRI is an educational tool designed to help you understand your "
            "lab results. Always consult your healthcare provider for medical "
            "decisions, diagnoses, or treatment plans."
        ),
    },
    {
        "category": "general",
        "question": "How accurate is the interpretation?",
        "answer": (
            "ALRI uses advanced AI models trained on medical literature to provide "
            "interpretations with 90% accuracy. Results are compared against "
            "standard reference ranges and cross-referenced for correlations."
        ),
    },
    # ── Account ───────────────────────────────────────────
    {
        "category": "account",
        "question": "How do I create an account?",
        "answer": (
            "Click 'Get Started' and sign in with your Google account or email. "
            "You'll receive \u20a65,000 in welcome credits to start analyzing "
            "your lab results."
        ),
    },
    {
        "category": "account",
        "question": "How do I update my profile?",
        "answer": (
            "Click the Settings icon in your dashboard sidebar to update your "
            "profile information including age, sex, and other details that help "
            "improve interpretation accuracy."
        ),
    },
    {
        "category": "account",
        "question": "Is my health data secure?",
        "answer": (
            "Yes. Your data is encrypted in transit and at rest. We never sell, "
            "share, or use your health information for advertising. ALRI is built "
            "to meet HIPAA compliance standards."
        ),
    },
    # ── Billing ───────────────────────────────────────────
    {
        "category": "billing",
        "question": "How much does it cost?",
        "answer": (
            "You get a free preview of your results without signing up. To unlock "
            "the full analysis \u2014 including AI health summary, risk correlations, "
            "and downloadable reports \u2014 create a free account and use your "
            "welcome credits."
        ),
    },
    {
        "category": "billing",
        "question": "How do I top up my account?",
        "answer": (
            "Click 'Top up' in your dashboard sidebar or the fund account button. "
            "We accept payments via Paystack (cards, bank transfer, USSD)."
        ),
    },
    {
        "category": "billing",
        "question": "What do credits cost?",
        "answer": (
            "Full scan unlock costs \u20a6200, each chat message costs \u20a650, "
            "skin analysis costs \u20a6250, and voice transcription costs \u20a6100."
        ),
    },
    {
        "category": "billing",
        "question": "Can I get a refund?",
        "answer": (
            "Credits are non-refundable once used. For billing disputes, please "
            "submit a support ticket and our team will review your case."
        ),
    },
    # ── Scans ─────────────────────────────────────────────
    {
        "category": "scans",
        "question": "What types of lab results can I upload?",
        "answer": (
            "ALRI supports common blood work panels including Complete Blood Count "
            "(CBC), metabolic panels, lipid panels, thyroid function, liver function, "
            "and more. You can upload PDFs, images (JPG, PNG, HEIC), or enter "
            "values manually."
        ),
    },
    {
        "category": "scans",
        "question": "Why did my scan fail?",
        "answer": (
            "Scans can fail if the image is blurry, the PDF is password-protected, "
            "or the lab format is not recognized. Try re-uploading a clearer image "
            "or entering values manually."
        ),
    },
    {
        "category": "scans",
        "question": "How do I view my scan history?",
        "answer": (
            "Go to 'Scan History' in your dashboard sidebar to see all your past "
            "scans with their status and results."
        ),
    },
    # ── Skin Analysis ─────────────────────────────────────
    {
        "category": "skin_analysis",
        "question": "How does skin analysis work?",
        "answer": (
            "Upload a clear photo of the skin area you want analyzed. Our AI will "
            "identify potential conditions, severity, and provide recommendations. "
            "This is a paid feature requiring a funded account."
        ),
    },
    {
        "category": "skin_analysis",
        "question": "Why can't I access skin analysis?",
        "answer": (
            "Skin analysis requires a funded account. You need to top up your "
            "account with real funds (signup bonus credits are not eligible) to "
            "unlock it."
        ),
    },
    # ── Technical ─────────────────────────────────────────
    {
        "category": "technical",
        "question": "The app is running slowly. What should I do?",
        "answer": (
            "Try refreshing the page, clearing your browser cache, or switching to "
            "a different browser. If the issue persists, please submit a support "
            "ticket."
        ),
    },
    {
        "category": "technical",
        "question": "Can I use ALRI on my phone?",
        "answer": (
            "Yes! ALRI is a Progressive Web App. Visit alri.health on your phone's "
            "browser and add it to your home screen for a native app experience."
        ),
    },
    {
        "category": "technical",
        "question": "My payment went through but credits weren't added.",
        "answer": (
            "Payments are usually processed within a few seconds. If credits "
            "haven't appeared after 5 minutes, please submit a support ticket with "
            "your payment reference number."
        ),
    },
]


def get_faq_context() -> str:
    """Build a text block of all FAQs for use as AI support chat context."""
    lines = []
    for item in SUPPORT_FAQ:
        lines.append(f"Q: {item['question']}")
        lines.append(f"A: {item['answer']}")
        lines.append("")
    return "\n".join(lines)
