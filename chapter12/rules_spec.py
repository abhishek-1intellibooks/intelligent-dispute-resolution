"""Source text for the synthetic rules library (read by make_data.py).

Each of the 23 topics is written once as a core requirement, with one phrase
that differs between the two networks and one that differs between the
superseded and the current edition. make_data.py combines them into
23 x 2 networks x 2 editions = 92 passages and adds 5 general passages on
regulation, tone and privacy, for 97 in all. The three questions under each
topic are paraphrases used by evaluate.py to test retrieval.

All of this text is synthetic. It imitates the shape of card network dispute
rules without reproducing any network's actual rules.
"""

FAMILIES = {
    "NR": "not_received",
    "ND": "not_as_described",
    "CR": "cancelled_recurring",
    "CN": "credit_not_processed",
    "DP": "duplicate_processing",
    "FR": "fraud_card_absent",
}

# Editions: (edition, effective_from, effective_to). None means still in force.
EDITIONS = {
    "A": [("2024.2", "2024-10-01", "2025-09-30"), ("2025.2", "2025-10-01", None)],
    "B": [("2024.1", "2024-04-12", "2025-04-10"), ("2025.1", "2025-04-11", None)],
}

# code, core, (q1, q2, q3), network A phrase, network B phrase, old phrase, new phrase
TOPICS = [
    ("NR1",
     "For a goods-not-received dispute the merchant must provide proof of delivery to the "
     "address the cardholder supplied, showing the carrier, the tracking number and the date "
     "the parcel was delivered.",
     ("What delivery proof does a merchant need to show when the cardholder says the goods never came?",
      "Which carrier details must accompany evidence that a parcel reached the cardholder's address?",
      "How does a merchant demonstrate that the order was delivered to the right address with tracking?"),
     "The acquirer submits the carrier's own record within 30 calendar days of the chargeback.",
     "The response must reach the issuer within 20 business days and include the full shipping manifest.",
     "A courier receipt without a photograph is accepted for any amount.",
     "Above 250 dollars a delivery photograph or signature is mandatory."),
    ("NR2",
     "When goods were shipped to an address other than the one the cardholder gave, the "
     "merchant cannot rely on proof of delivery and the claim is generally upheld for the cardholder.",
     ("What happens if the parcel was sent to a different address than the cardholder provided?",
      "Can a merchant defend a non-receipt claim when the shipping address differs from the cardholder's address?",
      "Is delivery to an address the cardholder did not give enough to defeat the dispute?"),
     "The issuer may add a cardholder letter naming the correct address.",
     "A redirected shipment counts only if the cardholder requested the change in writing.",
     "Billing and shipping postcodes must both be listed.",
     "Geolocation of the delivery scan may replace the postcode comparison."),
    ("NR3",
     "For digital goods or services not provided, the merchant shows that the download, login "
     "or access was completed by the cardholder's account after the purchase.",
     ("How does a seller prove that a digital download or online service was actually accessed?",
      "What evidence shows the cardholder's account used the service it says it never got?",
      "Which access logs count as proof for an online purchase that was allegedly not provided?"),
     "Server logs must carry the account identifier and a timestamp.",
     "Device fingerprint records are accepted alongside the IP address history.",
     "One successful login is sufficient.",
     "Two separate sessions of use are required after the purchase date."),
    ("NR4",
     "A cardholder must wait until the expected delivery date has passed before disputing "
     "non-receipt, unless the merchant has confirmed that the goods will not be sent.",
     ("How long must a customer wait before filing a not received dispute when no date was promised?",
      "Can a non-receipt claim be raised before the promised delivery date?",
      "When is it too early for a cardholder to say the goods never arrived?"),
     "If no date was given the cardholder waits 15 calendar days from the transaction.",
     "If no date was given the cardholder waits 30 days from the purchase.",
     "The waiting period applies to services as well as goods.",
     "The waiting period no longer applies to cancelled services."),
    ("ND1",
     "For merchandise not as described the cardholder must explain how the goods differed from "
     "the description at the time of purchase, and the merchant may respond with the listing and photographs.",
     ("What must a customer show when the item received did not match the online listing?",
      "How does a merchant answer a claim that the product differed from its description?",
      "What evidence is used when merchandise is said to differ from its description?"),
     "Expert opinion is optional for items under 500 dollars.",
     "An independent appraisal is needed for jewellery and art.",
     "The original advertisement must be supplied as a screenshot.",
     "An archived copy of the product page with its date is acceptable."),
    ("ND2",
     "Before a not-as-described dispute the cardholder must attempt to return the merchandise, "
     "and proof of return shipment or the merchant's refusal of the return supports the claim.",
     ("Does the cardholder have to send the item back before disputing it as not as described?",
      "What proof of returning the goods supports a quality complaint?",
      "Is a return attempt required when the merchandise is defective?"),
     "Return tracking must show delivery to the merchant's returns address.",
     "A postal receipt showing dispatch of the parcel back to the seller is enough.",
     "Returns are required for all items regardless of value.",
     "Items under 25 dollars are exempt from the return requirement."),
    ("ND3",
     "For counterfeit merchandise the cardholder provides a statement from the brand owner, a "
     "customs authority or a qualified expert that the goods are not genuine.",
     ("What proof is needed to claim that purchased goods were fake?",
      "Who can certify that an item is a counterfeit for a dispute?",
      "How is a claim of non-genuine branded goods supported?"),
     "The cardholder need not return counterfeit goods to the merchant.",
     "Counterfeit goods must be destroyed or retained, never sent back.",
     "A cardholder's own statement may be accepted for items under 100 dollars.",
     "A third-party statement is required at every value."),
    ("ND4",
     "The cardholder must make a good-faith attempt to resolve a quality dispute with the "
     "merchant before the issuer raises it, and must describe that attempt.",
     ("Must a customer first contact the seller about poor quality goods before disputing?",
      "What counts as an attempt to settle a quality problem with the merchant?",
      "Is it necessary to describe contact with the merchant in a quality dispute?"),
     "The attempt is described in the cardholder's own words with its date.",
     "Email or chat transcripts with the merchant are attached where they exist.",
     "Telephone contact alone satisfies the requirement.",
     "Contact must be made through a channel that leaves a written record."),
    ("CR1",
     "For a cancelled recurring transaction the cardholder shows that the subscription was "
     "cancelled before the charge, with the cancellation date and any confirmation number.",
     ("What must a cardholder show to prove the subscription was cancelled before it was charged?",
      "How is a charge after cancelling a membership disputed?",
      "Which details about the cancellation must accompany a recurring billing claim?"),
     "A cancellation confirmation code from the merchant is the preferred evidence.",
     "The issuer may rely on the cardholder's dated account of the cancellation.",
     "Cancellation must have occurred at least 3 days before billing.",
     "Cancellation any time before the billing date qualifies."),
    ("CR2",
     "A merchant defending a recurring charge must show that its cancellation terms were "
     "clearly disclosed and accepted by the cardholder at sign-up.",
     ("How can a subscription merchant show its cancellation terms were agreed by the customer?",
      "What disclosure of subscription terms helps the merchant win a recurring dispute?",
      "Does the merchant need proof the cardholder accepted the cancellation policy when enrolling?"),
     "A checkbox record with a timestamp is required.",
     "The terms must appear on the same screen as the payment button.",
     "Terms in the general conditions are acceptable.",
     "Terms must be shown separately from the general conditions."),
    ("CR3",
     "When a free trial converts to a paid subscription, the merchant must have told the "
     "cardholder the price, the conversion date and how to cancel before the first charge.",
     ("What must a merchant tell a customer before a free trial turns into a paid plan?",
      "Is a charge after a trial ended disputable if the price was not disclosed?",
      "What notice is required ahead of the first charge following a trial?"),
     "A reminder must be sent 7 days before the first charge.",
     "A reminder must be sent at least 3 days before conversion.",
     "The reminder may be sent by email only.",
     "The reminder must be sent through the channel used at enrolment."),
    ("CR4",
     "For annual renewals the merchant must notify the cardholder of the upcoming renewal and "
     "its amount, and a dispute succeeds if no notice was sent.",
     ("Does a merchant need to warn a customer before renewing a yearly subscription?",
      "What notice of an annual renewal charge is required?",
      "Can a cardholder dispute a yearly renewal they were never reminded about?"),
     "Notice is due between 30 and 60 days before renewal.",
     "Notice is due at least 14 days before renewal.",
     "Notice is required only for amounts above 50 dollars.",
     "Notice is required for every renewal amount."),
    ("CN1",
     "For credit not processed the cardholder provides the credit voucher, refund "
     "acknowledgment or return receipt showing that the merchant agreed to refund.",
     ("What documents show that a merchant promised a refund that never arrived?",
      "How does a customer prove a refund was agreed but not credited?",
      "Which receipt supports a claim that the merchant failed to issue a credit?"),
     "An undated voucher is accepted if the transaction reference appears on it.",
     "The voucher must be dated and show the amount of the credit.",
     "A verbal promise of refund recorded by the issuer is sufficient.",
     "A verbal promise must be confirmed in writing by the merchant."),
    ("CN2",
     "A merchant may defend a refund claim by showing a disclosed no-refund or store-credit "
     "policy that the cardholder accepted at purchase.",
     ("Can a seller refuse a refund if its store credit only policy was disclosed?",
      "How does a no refunds policy affect a credit not processed dispute?",
      "What evidence of a refund policy helps a merchant defend a refund claim?"),
     "The policy must be printed on the receipt.",
     "The policy must be shown before the cardholder pays.",
     "Policies posted at the till are accepted.",
     "Policies must be acknowledged by the cardholder."),
    ("CN3",
     "The cardholder must allow the merchant time to process a promised credit before "
     "disputing, counted from the date on the credit voucher or the return.",
     ("How long should a customer wait for a refund before opening a dispute?",
      "When can a cardholder dispute a promised credit that has not been processed yet?",
      "What is the waiting time for a promised credit to appear?"),
     "The waiting time is 15 calendar days.",
     "The waiting time is 10 business days.",
     "No waiting time applies if the voucher is undated.",
     "An undated voucher starts the waiting time on the return date."),
    ("CN4",
     "Where a merchant issued only part of the promised credit, the dispute is limited to the "
     "unrefunded difference.",
     ("What can be disputed when a merchant refunded only some of the money?",
      "Is the full amount disputable if a partial refund was given?",
      "How is a dispute calculated after a partial credit from the merchant?"),
     "Restocking fees disclosed at purchase are not disputable.",
     "Restocking fees are disputable unless shown on the receipt.",
     "The cardholder must state the partial amount received.",
     "The issuer calculates the difference from clearing records."),
    ("DP1",
     "For duplicate processing the issuer shows two transactions with the same card, merchant, "
     "amount and date, and the merchant may answer with proof of two separate purchases.",
     ("How is a charge that appears twice on a statement disputed?",
      "What proves that a merchant processed the same sale two times?",
      "Can two charges with the same card, amount and date be disputed as duplicate processing?"),
     "The two transactions must share the authorization code.",
     "Matching acquirer reference numbers are strong evidence of duplication.",
     "Transactions within 7 days qualify.",
     "Transactions within 15 days qualify."),
    ("DP2",
     "When a cardholder paid for the same goods by another method, the cardholder supplies "
     "proof of the other payment, such as a cash receipt or a bank transfer record.",
     ("What evidence is needed when a customer paid twice using cash and card?",
      "How does a cardholder show they settled the bill by another payment method?",
      "What documents support a claim that the purchase was already paid another way?"),
     "The other payment must be to the same merchant outlet.",
     "Payment to any outlet of the same merchant is accepted.",
     "A bank statement line is sufficient proof.",
     "A receipt from the merchant is required for cash payments."),
    ("DP3",
     "A merchant defending a duplicate claim provides itemized receipts or order records "
     "showing that each transaction was a separate purchase.",
     ("Which itemized receipts show that two similar charges were different orders?",
      "What records prove that two charges were for separate items?",
      "What defence does a seller have against a claim of being billed twice?"),
     "Each receipt must show a distinct order number.",
     "Each receipt must show the time of sale to the minute.",
     "Signed receipts are required for both transactions.",
     "Unsigned electronic receipts are accepted."),
    ("FR1",
     "For card-absent fraud the merchant may submit compelling evidence that the same "
     "cardholder made earlier undisputed purchases using the same device or account.",
     ("What history of earlier purchases can a merchant use against a fraud claim?",
      "How do previous undisputed orders help a merchant fight an unauthorized online transaction?",
      "What prior transaction evidence defeats a card not present fraud dispute?"),
     "Two prior transactions between 120 and 365 days old are required.",
     "One prior transaction within 180 days is required.",
     "Matching shipping address alone links the transactions.",
     "At least two data elements must match, such as device and IP address."),
    ("FR2",
     "A merchant may show that address verification and the card security code matched at "
     "authorization when answering a card-absent fraud claim.",
     ("Does a matching security code help a merchant defend an unauthorized purchase?",
      "What role does address verification play in fraud disputes?",
      "Can successful CVV and AVS checks be used as evidence against a fraud claim?"),
     "A full AVS match must be shown in the authorization record.",
     "A partial AVS match is accepted with a CVV match.",
     "AVS alone was sufficient evidence.",
     "AVS results are supporting evidence only."),
    ("FR3",
     "When a card-absent transaction was authenticated with 3-D Secure, fraud liability shifts "
     "to the issuer and the merchant cites the authentication value.",
     ("Who bears the loss on an online fraud claim when strong authentication was used?",
      "How does a successful cardholder authentication affect liability for a fraud dispute?",
      "What does the merchant cite to show the purchase was authenticated?"),
     "The shift applies only to fully authenticated transactions.",
     "Attempted authentication also shifts liability.",
     "Version 1 authentication is accepted.",
     "Only version 2 authentication shifts liability."),
    ("FR4",
     "A merchant may rely on device identifiers, IP addresses and login history linking the "
     "disputed purchase to the cardholder's prior activity.",
     ("Can a seller use login history and device identifiers to link the purchase to the cardholder?",
      "What digital fingerprint evidence links a fraud dispute to the real cardholder?",
      "How do login records help a merchant contest an unauthorized charge?"),
     "The IP address must be shown with the geolocation.",
     "The device identifier must persist across sessions.",
     "Email address match is sufficient.",
     "Email match must be combined with a device match."),
]

GENERAL = [
    ("R-G-REGE", "regulation",
     "Regulation E requires a financial institution to investigate an error reported on a "
     "debit card account within 10 business days, or within 45 days if it gives provisional "
     "credit, and to report the results to the consumer in writing."),
    ("R-G-REGZ", "regulation",
     "Regulation Z requires a card issuer to acknowledge a billing error notice on a credit "
     "card within 30 days and to resolve it within two billing cycles and no more than 90 days."),
    ("R-G-TONE", "tone",
     "Letters to cardholders state what the records show, never accuse the cardholder, explain "
     "the next steps and the cardholder's rights, and use plain language."),
    ("R-G-PRIV1", "privacy",
     "Messages to merchants include only the data the network requires for the dispute; never "
     "send the cardholder's contact details or information about other accounts."),
    ("R-G-PRIV2", "privacy",
     "Card numbers, email addresses and telephone numbers are redacted from narratives before "
     "they are placed in prompts or logs."),
]
