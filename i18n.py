"""Interface language.

Why not flask-babel: it wants .po files compiled with pybabel as a build
step, and this app deploys by pushing to Render with no build stage beyond
pip install. A plain dict keeps translations editable by anyone who can read
Hindi, with no toolchain and nothing to compile.

Anything without a translation falls back to the English string, so a missing
entry shows English rather than a blank or a key — a half-translated screen
is usable, a screen full of 'nav.workers' is not.
"""

import re

LANGUAGES = {
    'en': 'English',
    'hi': 'हिन्दी',
}

DEFAULT_LANGUAGE = 'en'

#: English source string -> translation. Keyed by the English text itself so
#: a template reads _('Mark Attendance') and stays readable to someone who
#: does not know the translation layer exists.
TRANSLATIONS = {
    'hi': {
        # --- navigation and chrome ---------------------------------------
        'Home': 'होम',
        'Workers': 'मज़दूर',
        'Attendance': 'हाज़िरी',
        'Scan QR': 'QR स्कैन',
        'Transactions': 'लेन-देन',
        'Profile': 'प्रोफ़ाइल',
        'ID Entry': 'आईडी डालें',
        'Settings': 'सेटिंग',
        'Dashboard': 'डैशबोर्ड',
        'Payroll': 'वेतन',
        'Reports': 'रिपोर्ट',
        'Notifications': 'सूचनाएँ',
        'Assignments': 'साइट नियुक्ति',
        'Back': 'वापस',
        'Close': 'बंद करें',
        'Cancel': 'रद्द करें',
        'Save': 'सेव करें',
        'Delete': 'मिटाएँ',
        'Edit': 'बदलें',
        'Search': 'खोजें',
        'Filter': 'छाँटें',
        'Loading…': 'लोड हो रहा है…',

        # --- names for the controls that show only an icon ----------------
        # These reach nobody's eye; they are what a screen reader announces
        # and what a long press shows. A control with no name at all is a
        # guess until you press it and find out what it did.
        'Show password': 'पासवर्ड दिखाएँ',
        'Print': 'प्रिंट करें',
        'Download PDF': 'PDF डाउनलोड करें',
        'Share': 'साझा करें',
        'Export': 'एक्सपोर्ट करें',
        'Archive': 'संग्रह में डालें',
        'Restore': 'वापस लाएँ',
        'Closure days': 'बंदी के दिन',
        'Previous day': 'पिछला दिन',
        'Next day': 'अगला दिन',
        'Previous month': 'पिछला महीना',
        'Next month': 'अगला महीना',
        'Calendar': 'कैलेंडर',
        'Edit Worker': 'मज़दूर में बदलाव',
        'Update Profile Information': 'प्रोफ़ाइल की जानकारी बदलें',
        'Enter the new worker’s details': 'नए मज़दूर की जानकारी भरें',
        'Change photo': 'फ़ोटो बदलें',
        'Add a transaction': 'लेन-देन जोड़ें',
        'Statistics': 'आँकड़े',
        'More actions': 'और विकल्प',
        'ID card': 'पहचान पत्र',
        'Open this worker': 'इस मज़दूर को खोलें',
        'Mark all as read': 'सब पढ़ा हुआ चिह्नित करें',

        # --- attendance ---------------------------------------------------
        'Present': 'हाज़िर',
        'Absent': 'ग़ैरहाज़िर',
        'Late': 'देर से',
        'Leave': 'छुट्टी',
        'Half Day': 'आधा दिन',
        'Not marked': 'दर्ज नहीं',
        'Unmarked': 'दर्ज नहीं',
        'Paid Days': 'वेतन वाले दिन',
        'Mark Attendance': 'हाज़िरी लगाएँ',
        'All present': 'सब हाज़िर',
        'All absent': 'सब ग़ैरहाज़िर',
        'Close shifts': 'शिफ़्ट बंद करें',
        'Adjust times': 'समय बदलें',
        "Today's Attendance": 'आज की हाज़िरी',
        'Attendance Calendar': 'हाज़िरी कैलेंडर',
        'Attendance Rate': 'हाज़िरी दर',
        'Check In': 'आने का समय',
        'Check Out': 'जाने का समय',
        'Closure Day': 'छुट्टी का दिन',
        'Daily Attendance Management': 'रोज़ की हाज़िरी',
        'Select Date': 'तारीख़ चुनें',
        'Mark': 'लगाएँ',
        'today': 'आज',
        'These apply to': 'ये लागू होंगे',
        'Workers on this date': 'इस दिन के मज़दूर',
        'No workers were on the roll on this date.':
            'इस तारीख़ को कोई मज़दूर रजिस्टर में नहीं था।',
        'shift open': 'शिफ़्ट खुली',
        'Transactions on this date': 'इस दिन के लेन-देन',
        'Transaction': 'लेन-देन',
        'Scan or type employee ID': 'आईडी स्कैन करें या टाइप करें',
        'Tap the same status twice to check out and bank overtime.':
            'उसी बटन को दोबारा दबाएँ — जाने का समय दर्ज होगा और ओवरटाइम जुड़ेगा।',
        'Shift open': 'शिफ़्ट खुली',
        'Add transaction': 'लेन-देन जोड़ें',
        'Add closure': 'छुट्टी जोड़ें',
        'Mark %n %s absent for this date?':
            'इस तारीख़ के लिए %n %s को ग़ैरहाज़िर लगाना है?',
        'Mark %n %s on leave for this date?':
            'इस तारीख़ के लिए %n %s को छुट्टी पर लगाना है?',
        'Mark every listed worker as this status for this date?':
            'इस तारीख़ के लिए सूची के सभी मज़दूरों पर यही हालत लगानी है?',
        'Mark every listed worker as this status on':
            'सूची के सभी मज़दूरों पर यही हालत लगानी है',
        'Close every open shift on': 'इस दिन की सभी खुली शिफ़्ट बंद करनी हैं',
        # Leave types, stored in English on the record. 'Paid' and 'Unpaid'
        # are deliberately absent: 'Paid' is already the payroll status
        # ('दे दिया') and a second entry would silently overwrite it.
        'Casual': 'आम',
        'Sick': 'बीमारी',
        'Earned': 'जमा की हुई',
        'Nothing recorded for this date.': 'इस तारीख़ का कोई रिकॉर्ड नहीं।',
        'cancelled': 'रद्द',
        'Press and hold a worker to mark several at once.':
            'एक साथ कई की हाज़िरी लगाने के लिए किसी मज़दूर को दबाकर रखें।',
        'Saved on this phone. Will upload when internet returns.':
            'इस फ़ोन में सेव हो गया। इंटरनेट आते ही अपने-आप भेज दिया जाएगा।',
        'No internet. Attendance saved on this phone and will upload automatically.':
            'इंटरनेट नहीं है। हाज़िरी इस फ़ोन में सेव हो गई और अपने-आप भेज दी जाएगी।',

        # --- workers ------------------------------------------------------
        'Add Worker': 'मज़दूर जोड़ें',
        'Total Workers': 'कुल मज़दूर',
        'Worker ID': 'मज़दूर आईडी',
        'Full Name': 'पूरा नाम',
        'Phone': 'फ़ोन',
        'Department': 'विभाग',
        'Position': 'पद',
        'Joining Date': 'भर्ती की तारीख़',
        'Daily Wage': 'दिहाड़ी',
        'Monthly Salary': 'महीने की तनख़्वाह',
        'Active': 'चालू',
        'Inactive': 'बंद',
        'Previous': 'पिछला',
        'Next': 'अगला',

        # --- money and payroll --------------------------------------------
        'Salary': 'तनख़्वाह',
        'Daily salary': 'एक दिन की तनख़्वाह',
        'Advance': 'पेशगी',
        'Bonus': 'इनाम',
        'Deduction': 'कटौती',
        'Deductions': 'कटौतियाँ',
        'Net Payable': 'देने योग्य रक़म',
        'Gross Pay': 'कुल रक़म',
        'Total Deduction': 'कुल कटौती',
        'Paid': 'दे दिया',
        'Pending': 'बाक़ी',
        'Overtime': 'ओवरटाइम',
        'Generate Payroll': 'वेतन बनाएँ',
        'Payroll Preview': 'वेतन का पूर्वावलोकन',
        'Payslip': 'तनख़्वाह पर्ची',
        'Salary Calculation': 'तनख़्वाह का हिसाब',
        'How this was calculated': 'यह हिसाब कैसे लगा',

        # --- payslip --------------------------------------------------------
        'Payroll Slip': 'तनख़्वाह पर्ची',
        'PAYSLIP': 'तनख़्वाह पर्ची',
        'Building PDF…': 'PDF बन रही है…',
        'Payroll Department': 'वेतन विभाग',
        'PAID': 'दे दिया',
        'PENDING': 'बाक़ी',
        'Attendance Summary': 'हाज़िरी का ब्योरा',
        'Pay Breakdown': 'रक़म का ब्योरा',
        'Daily Rate': 'दिहाड़ी',
        '/ day': '/ दिन',
        'day': 'दिन',
        'Full Days': 'पूरे दिन',
        'Half Days': 'आधे दिन',
        'Pro-Rata Days': 'हिस्से के दिन',
        'Paid Absent Days': 'ग़ैरहाज़िरी के भुगतान वाले दिन',
        'Leave Days': 'छुट्टी के दिन',
        'extra': 'अतिरिक्त',
        'Worked Hours': 'काम के घंटे',
        'hrs': 'घंटे',
        'Hourly Rate': 'घंटे का रेट',
        '/ hr': '/ घंटा',
        'Project Rate': 'प्रोजेक्ट रेट',
        'Base Pay': 'मूल रक़म',
        'Closure Day Bonus': 'छुट्टी के दिन का इनाम',
        'min': 'मिनट',
        'Bonus / Extra Payments': 'इनाम / अतिरिक्त भुगतान',
        'Leave Deduction': 'छुट्टी की कटौती',
        'day(s) beyond balance': 'दिन बची छुट्टी से ज़्यादा',
        'Late Deduction': 'देर से आने की कटौती',
        'Project Delay Penalty': 'प्रोजेक्ट देरी की कटौती',
        'Advances / Loans / Recoveries': 'पेशगी / क़र्ज़ / वसूली',
        'Leave Balance (since joining)': 'छुट्टी का हिसाब (भर्ती से अब तक)',
        'Quota/mo': 'महीने का हक़',
        'Carried': 'आगे बढ़ी',
        'Used': 'ली गई',
        'Remaining': 'बची',
        'Transactions This Month': 'इस महीने के लेन-देन',
        'Closure Day Bonus Breakdown': 'छुट्टी के इनाम का ब्योरा',
        # --- the salary calculation table (payslip and worker report) ------
        'Employee': 'मज़दूर',
        'Employee ID': 'मज़दूर आईडी',
        'Joining date': 'भर्ती की तारीख़',
        'Monthly fixed salary': 'महीने की तय तनख़्वाह',
        'Calculation basis': 'हिसाब का आधार',
        'Daily salary (exact)': 'एक दिन की तनख़्वाह (पूरी)',
        'Daily salary (rounded)': 'एक दिन की तनख़्वाह (गोल की हुई)',
        'Total calendar days': 'महीने के कुल दिन',
        'Eligible salary days': 'तनख़्वाह वाले दिन',
        'Present days': 'हाज़िर दिन',
        'Absent days': 'ग़ैरहाज़िर दिन',
        'Paid leave allowance': 'मिलने वाली छुट्टी',
        'Paid leave used': 'ली गई छुट्टी',
        'Unpaid leave': 'बिना तनख़्वाह की छुट्टी',
        'Total deduction days': 'कटौती वाले कुल दिन',
        'Deduction rate': 'कटौती का रेट',
        'Total salary deduction': 'कुल तनख़्वाह कटौती',
        'Gross eligible salary': 'कुल बनने वाली तनख़्वाह',
        'Final net payable salary': 'आख़िर में देने योग्य तनख़्वाह',
        'days': 'दिन',
        # salary.LABELS — the policy wording shown on the slip and in settings
        'Fixed days': 'तय दिन',
        'Actual calendar days': 'महीने के असली दिन',
        'No rounding': 'गोल नहीं करना',
        'Nearest rupee': 'नज़दीकी रुपए तक',
        'Always round up': 'हमेशा ऊपर',
        'Always round down': 'हमेशा नीचे',
        'Calendar days from joining date': 'भर्ती की तारीख़ से कैलेंडर के दिन',
        'Actual attendance since joining': 'भर्ती के बाद की असली हाज़िरी',
        'Monthly salary minus deductions': 'महीने की तनख़्वाह में से कटौती',
        'Daily rate x payable days': 'दिहाड़ी × देने योग्य दिन',

        # --- worker profile report -----------------------------------------
        'Employee Report': 'मज़दूर की रिपोर्ट',
        'Profile Report': 'प्रोफ़ाइल रिपोर्ट',
        'Personal & Employment Details': 'निजी और नौकरी की जानकारी',
        'Joined': 'भर्ती',
        'Pay Type': 'मज़दूरी का तरीक़ा',
        'Current Assignment': 'अभी कहाँ लगे हैं',
        'Project': 'प्रोजेक्ट',
        'Site': 'साइट',
        'Task': 'काम',
        'Since': 'कब से',
        'Not currently assigned.': 'अभी कहीं नहीं लगे हैं।',
        'Leave Balance': 'छुट्टी का हिसाब',
        'Monthly Quota': 'महीने का हक़',
        'day(s)': 'दिन',
        'Accrued (since joining)': 'जमा हुई (भर्ती से)',
        'Manual Adjustments': 'हाथ से किए बदलाव',
        'Used This Month': 'इस महीने ली गई',
        'Available Balance': 'बची हुई छुट्टी',
        'Leave policy not applicable.': 'छुट्टी का नियम लागू नहीं है।',
        'Project & Site History': 'प्रोजेक्ट और साइट का इतिहास',
        'Project / Site': 'प्रोजेक्ट / साइट',
        'From': 'से',
        'To': 'तक',
        'Days': 'दिन',
        'No project or site assignments recorded.':
            'किसी प्रोजेक्ट या साइट पर लगने का रिकॉर्ड नहीं है।',
        'Promotions & Modification History': 'तरक़्क़ी और बदलावों का इतिहास',
        'Change': 'बदलाव',
        'Details': 'ब्योरा',
        'No modifications recorded since joining.':
            'भर्ती के बाद से कोई बदलाव दर्ज नहीं है।',
        'Attendance & Pay — Last 6 Months': 'हाज़िरी और मज़दूरी — पिछले 6 महीने',
        'Month': 'महीना',
        'Net Pay': 'देने योग्य रक़म',
        'P = Present, L = Late, A = Absent, Lv = Leave. Net pay includes '
        'overtime, transactions and deductions.':
            'P = हाज़िर, L = देर से, A = ग़ैरहाज़िर, Lv = छुट्टी। देने योग्य रक़म में '
            'ओवरटाइम, लेन-देन और कटौतियाँ शामिल हैं।',
        'No attendance history yet.': 'अभी हाज़िरी का कोई इतिहास नहीं है।',
        'OT': 'ओवरटाइम',
        'Daily': 'दिहाड़ी',
        'Monthly': 'महीनेवार',
        'Hourly': 'घंटेवार',
        # TRANSACTION_TYPE_LABELS in routes.py
        'Advance Salary': 'पेशगी तनख़्वाह',
        'Loan': 'क़र्ज़',
        'Cash Advance': 'नक़द पेशगी',
        'Recovery': 'वसूली',
        'Extra Payment': 'अतिरिक्त भुगतान',
        'Incentive': 'प्रोत्साहन राशि',
        'Refreshment Allowance': 'नाश्ते का भत्ता',
        # Wages themselves being paid, as against an advance on them. The
        # distinction is the whole point of the type, so the Hindi has to
        # carry it too: पेशगी is money taken early, this is the मज़दूरी.
        'Wages Paid': 'मज़दूरी दी गई',
        # 'Deducted from pay' and 'Added to pay', the other two optgroups,
        # are already in this table further down.
        'Settles wages owed': 'बाक़ी मज़दूरी चुकाता है',
        # PAYMENT_MODE_LABELS in routes.py
        'Cash': 'नक़द',
        'UPI': 'UPI',
        'Bank Transfer': 'बैंक ट्रांसफ़र',
        'Cheque': 'चेक',
        'Paid by': 'कैसे दिया',
        'Reference': 'संदर्भ',
        'Ref': 'संदर्भ',
        'UTR / cheque no.': 'UTR / चेक नं.',
        'Not recorded': 'दर्ज नहीं',
        'Advances': 'पेशगी',
        'Wages Paid This Month': 'इस महीने दी गई मज़दूरी',
        'Wages paid this month': 'इस महीने दी गई मज़दूरी',
        'Wages paid': 'दी गई मज़दूरी',
        "Wages Paid does not change the month's net — it records money handed over against what is owed.":
            'मज़दूरी दी गई से महीने की रक़म नहीं बदलती — यह सिर्फ़ दर्ज करता है कि '
            'बाक़ी के बदले कितना पैसा दिया गया।',
        # Part settlement — payroll screen and the running account
        'Part Paid': 'आधा दिया',
        'Part paid': 'आधा दिया',
        'No work': 'काम नहीं',
        'Record a payment': 'भुगतान दर्ज करें',
        'Record a part payment for': 'इनके लिए आंशिक भुगतान दर्ज करें',
        'Total paid for this month (₹)': 'इस महीने का कुल दिया गया (₹)',
        'still owed': 'अभी बाक़ी',
        # The running account and the company-wide dues screen
        'Wages Owed': 'बाक़ी मज़दूरी',
        'Total still owed': 'कुल बाक़ी',
        'workers waiting': 'मज़दूरों का बाक़ी है',
        'Unpaid since': 'इस महीने से बाक़ी',
        'months open': 'महीने बाक़ी',
        'since': 'से',
        'Open account': 'खाता खोलें',
        'Payment details on file': 'भुगतान की जानकारी दर्ज है',
        'No bank or UPI on file': 'बैंक या UPI दर्ज नहीं',
        'of the workers owed money have no bank account or UPI id on file.':
            'मज़दूरों का पैसा बाक़ी है लेकिन उनका बैंक खाता या UPI दर्ज नहीं है।',
        'Nothing is owed. Every month is settled.':
            'कुछ बाक़ी नहीं। हर महीना चुकता है।',
        'Showing the first': 'पहले',
        'workers by joining date. The totals below cover only those.':
            'मज़दूर दिखाए जा रहे हैं (भर्ती की तारीख़ से)। नीचे का जोड़ इन्हीं का है।',
        'Settled on the payroll screen': 'तनख़्वाह स्क्रीन से चुकाया गया',
        'Paid in': 'दिया गया',
        'counted against this month': 'इस महीने के बाक़ी में गिना गया',
        'part of': 'इसमें से',
        'See what is owed': 'देखें क्या बाक़ी है',
        'How payments are counted': 'भुगतान कैसे गिना जाए',
        'When a worker is owed several months and is given an amount, this decides which month it clears. It changes nothing about what anyone is owed in total — only which month shows the arrears.':
            'जब किसी मज़दूर के कई महीने बाक़ी हों और उसे कोई रक़म दी जाए, तो यह तय '
            'करता है कि वह किस महीने का हिसाब चुकाएगी। किसी का कुल बाक़ी इससे नहीं '
            'बदलता — सिर्फ़ यह बदलता है कि बाक़ी किस महीने पर दिखे।',
        'Against the month it was paid in': 'जिस महीने में दिया, उसी महीने में',
        'An amount handed over in October counts against October. Suits a business that settles one month at a time.':
            'अक्टूबर में दी गई रक़म अक्टूबर के हिसाब में जाएगी। उस कारोबार के लिए ठीक '
            'है जो एक-एक महीना चुकाता है।',
        'Against the oldest unpaid month first': 'सबसे पुराने बाक़ी महीने में पहले',
        'An amount handed over in October clears August first, then September. Suits a business that pays off arrears as cash allows.':
            'अक्टूबर में दी गई रक़म पहले अगस्त का हिसाब चुकाएगी, फिर सितम्बर का। उस '
            'कारोबार के लिए ठीक है जो पैसा आने पर पुराना बाक़ी चुकाता है।',
        # Confirming money was received
        'Confirm I received this': 'पुष्टि करें कि यह मुझे मिला',
        'Confirmed received': 'मिलने की पुष्टि हुई',
        'Confirmed received by the worker': 'मज़दूर ने मिलने की पुष्टि की',
        'Handed over in person': 'सामने दिया गया',
        'Not yet confirmed': 'अभी पुष्टि नहीं हुई',
        'Worker confirms receipt': 'मज़दूर मिलने की पुष्टि करता है',
        'My Account': 'मेरा खाता',
        # Stored enum values shown with .title() in templates
        'Holiday': 'त्योहार/छुट्टी',
        'Weather': 'मौसम',
        'Emergency': 'आपात',
        'Maintenance': 'मरम्मत',
        'Completed': 'पूरा हुआ',
        'On_hold': 'रुका हुआ',
        'No pay rate': 'मज़दूरी तय नहीं',
        'Payment Details': 'भुगतान की जानकारी',
        'Where the money goes. Every field is optional — fill in what you have.':
            'पैसा कहाँ जाएगा। हर ख़ाना ज़रूरी नहीं — जो पता है वही भरें।',
        'Account Holder Name': 'खाताधारक का नाम',
        'Bank Account Number': 'बैंक खाता संख्या',
        'IFSC': 'IFSC',
        'UPI ID': 'UPI आईडी',
        'Aadhaar Number': 'आधार संख्या',
        'PAN': 'PAN',
        'Shown masked, and never printed on a payslip.':
            'ढकी हुई दिखती है, और तनख़्वाह पर्ची पर कभी नहीं छपती।',
        'No way to pay this worker is recorded yet.':
            'इस मज़दूर को पैसा भेजने का कोई ज़रिया अभी दर्ज नहीं है।',
        'My Attendance & Pay': 'मेरी हाज़िरी और मज़दूरी',
        'Something wrong with your attendance or pay? Speak to your supervisor — this screen is read-only.':
            'हाज़िरी या मज़दूरी में कुछ ग़लत लगे तो अपने सुपरवाइज़र से कहें — यह स्क्रीन सिर्फ़ दिखाने के लिए है।',
        'This login is not linked to a worker record. Please contact the Administrator.':
            'यह लॉगिन किसी मज़दूर से जुड़ा नहीं है। एडमिन से कहें।',
        'Worker Login': 'मज़दूर का लॉगिन',
        'Lets this worker see their own attendance and payslip, and nothing else.':
            'इससे यह मज़दूर सिर्फ़ अपनी हाज़िरी और पर्ची देख सकेगा, और कुछ नहीं।',
        'Create Login': 'लॉगिन बनाएँ',
        'Reset Password': 'पासवर्ड बदलें',
        'Remove Login': 'लॉगिन हटाएँ',
        'Remove this login?': 'यह लॉगिन हटाना है?',
        'My Team': 'मेरी टोली',
        'No workers have been assigned to you yet. Ask the Administrator.':
            'अभी आपको कोई मज़दूर नहीं सौंपा गया है। एडमिन से कहें।',
        "You can mark present and late. Absences, leave and any correction are the Administrator's to make.":
            'आप हाज़िर और देर से लगा सकते हैं। ग़ैरहाज़िरी, छुट्टी और कोई भी सुधार एडमिन का काम है।',
        'Team': 'टोली',
        'Assign Workers': 'मज़दूर सौंपें',
        'Can mark attendance': 'हाज़िरी लगा सकता है',
        'Can record transactions': 'लेन-देन दर्ज कर सकता है',
        'A supervisor can never mark their own attendance.':
            'मुकादम अपनी ख़ुद की हाज़िरी कभी नहीं लगा सकता।',
        'Present and late only, for the workers chosen below.':
            'सिर्फ़ हाज़िर और देर से, और सिर्फ़ नीचे चुने गए मज़दूरों के लिए।',
        'Can add an advance or payment, but never cancel or change one.':
            'पेशगी या भुगतान जोड़ सकता है, पर रद्द या बदल नहीं सकता।',
        'Only these workers appear on their list.':
            'उसकी सूची में सिर्फ़ यही मज़दूर दिखेंगे।',
        'Powers and team': 'अधिकार और टोली',
        'Read-only': 'सिर्फ़ देखने के लिए',
        'Policy in force': 'लागू नियम',
        # salary.describe() labels and its plain values
        'Salary basis': 'तनख़्वाह का आधार',
        'Daily rate rounding': 'दिहाड़ी का पूर्णांकन',
        'Mid-month joining': 'महीने के बीच भर्ती',
        'Paid leave': 'तनख़्वाह वाली छुट्टी',
        'Leave carry-forward': 'बची छुट्टी आगे बढ़ाना',
        'Absence deduction': 'ग़ैरहाज़िरी पर कटौती',
        'Calculation method': 'हिसाब का तरीक़ा',
        'On': 'चालू',
        'Off': 'बंद',
        'Disabled': 'बंद',
        'Ongoing': 'जारी',
        'Today': 'आज',
        # Day separators in the notifications feed, and the noun the folded
        # line counts ("3 workers — present").
        'Yesterday': 'कल',
        'workers': 'मज़दूर',
        'and %n more': 'और %n',
        'Checked Out': 'छुट्टी दर्ज',
        'Saved Payroll Records': 'सेव किए गए वेतन रिकॉर्ड',
        'Period': 'अवधि',
        'Net': 'देने योग्य',
        'Transaction History': 'लेन-देन का इतिहास',
        'Amount': 'रक़म',
        'No transactions recorded.': 'कोई लेन-देन दर्ज नहीं है।',
        'Worker Management System': 'मज़दूर प्रबंधन प्रणाली',

        # --- ID card --------------------------------------------------------
        'Employee ID Card': 'मज़दूर पहचान पत्र',
        'Digital Identity': 'डिजिटल पहचान',
        'Preparing ID card…': 'पहचान पत्र तैयार हो रहा है…',
        'Phone Number': 'फ़ोन नंबर',
        'Joined Date': 'भर्ती की तारीख़',
        'QR Code for Attendance': 'हाज़िरी के लिए QR कोड',
        'Valid for attendance marking': 'हाज़िरी लगाने के लिए मान्य',
        'Generated': 'बनाया गया',
        'Download ID': 'पहचान पत्र डाउनलोड करें',
        'Generate New QR': 'नया QR बनाएँ',
        'ID Card Information': 'पहचान पत्र की जानकारी',
        'Card Type': 'कार्ड की किस्म',
        'Digital Employee ID': 'डिजिटल मज़दूर पहचान',
        'QR Code Status': 'QR कोड की हालत',
        'Last Generated': 'पिछली बार बना',
        'QR Usage Statistics': 'QR के इस्तेमाल का हिसाब',
        'Successful Check-ins': 'सफल हाज़िरी',
        'This Week': 'इस हफ़्ते',
        'Other Records': 'बाक़ी रिकॉर्ड',
        'Success Rate': 'सफलता दर',
        'Download Options': 'डाउनलोड के विकल्प',
        'Choose your preferred format': 'अपनी पसंद का रूप चुनें',
        'PNG Image': 'PNG तस्वीर',
        'High quality image format': 'बढ़िया क्वालिटी की तस्वीर',
        'PDF Document': 'PDF दस्तावेज़',
        'Printable format': 'छापने लायक़ रूप',
        'QR Code': 'QR कोड',

        'Employer Signature': 'मालिक के हस्ताक्षर',
        'Employee Signature': 'मज़दूर के हस्ताक्षर',
        'Generated by': 'बनाया गया',
        'Print Slip': 'पर्ची छापें',
        'Save PDF': 'PDF सेव करें',
        'PDF generation failed. Use Print instead.':
            'PDF नहीं बन सकी। छापने वाला विकल्प इस्तेमाल करें।',
        'Back to Payroll': 'वेतन पर वापस',
        'Page %n of %t': 'पृष्ठ %n / %t',

        # --- common actions and messages ------------------------------------
        'Sign In': 'लॉगिन करें',
        'Professional Attendance Management': 'हाज़िरी का पूरा इंतज़ाम',
        'Welcome Back': 'वापसी पर स्वागत',
        'Access your attendance dashboard': 'अपना हाज़िरी डैशबोर्ड खोलें',
        'Username or Email': 'यूज़रनेम या ईमेल',
        'Remember me': 'मुझे याद रखें',
        'Forgot Password?': 'पासवर्ड भूल गए?',
        'Sign In to Dashboard': 'डैशबोर्ड में लॉगिन करें',
        'OR': 'या',
        'Mobile Number for OTP Login': 'OTP से लॉगिन के लिए मोबाइल नंबर',
        'Send OTP': 'OTP भेजें',
        'Verify & Login': 'जाँचें और लॉगिन करें',
        'Enter mobile number and use OTP to login.':
            'मोबाइल नंबर डालें और OTP से लॉगिन करें।',
        "Don't have an account?": 'खाता नहीं है?',
        'Create Account': 'खाता बनाएँ',
        'Enter username or email': 'यूज़रनेम या ईमेल डालें',
        'Enter your password': 'अपना पासवर्ड डालें',
        'Enter registered mobile number': 'रजिस्टर्ड मोबाइल नंबर डालें',
        'Enter 6-digit OTP': '6 अंकों का OTP डालें',
        'Sign Out': 'लॉगआउट',
        'Username': 'यूज़रनेम',
        'Password': 'पासवर्ड',
        'Saved': 'सेव हो गया',
        'Could not save': 'सेव नहीं हो सका',
        'No internet connection': 'इंटरनेट नहीं है',
        'Are you sure?': 'क्या आप निश्चित हैं?',
        'Yes': 'हाँ',
        'No': 'नहीं',
        'Language': 'भाषा',
        'Saved for this phone only, so a site phone can be in Hindi while '
        'the office stays in English.':
            'यह सिर्फ़ इस फ़ोन के लिए सेव होता है — साइट का फ़ोन हिन्दी में '
            'और दफ़्तर का अंग्रेज़ी में रह सकता है।',

        # --- month names, for the month pickers and report headings -------
        # Also reachable as MONTHS['hi'], but the pickers hand _() the English
        # name rather than a month number.
        'January': 'जनवरी', 'February': 'फ़रवरी', 'March': 'मार्च',
        'April': 'अप्रैल', 'May': 'मई', 'June': 'जून', 'July': 'जुलाई',
        'August': 'अगस्त', 'September': 'सितंबर', 'October': 'अक्टूबर',
        'November': 'नवंबर', 'December': 'दिसंबर',

        # --- dashboard ----------------------------------------------------
        'Dashboard Overview': 'एक नज़र में',
        'Welcome back': 'स्वागत है',
        'Present Today': 'आज हाज़िर',
        'Absent Today': 'आज ग़ैरहाज़िर',
        'Calculate & track monthly wages': 'महीने की मज़दूरी का हिसाब रखें',
        'Quick Actions': 'तुरंत काम',
        'QR Scanner': 'QR स्कैनर',
        'Closures': 'छुट्टी के दिन',
        'Upcoming Closures': 'आगे की छुट्टियाँ',
        'View All': 'सब देखें',
        'Worker': 'मज़दूर',
        'In': 'आए',
        'Out': 'गए',
        'Status': 'हालत',
        'shift': 'शिफ़्ट',

        # --- workers list ---------------------------------------------------
        'Manage Employee Records': 'मज़दूरों का रिकॉर्ड',
        'All Departments': 'सभी विभाग',
        'Press and hold a worker to select several at once.':
            'एक साथ कई चुनने के लिए किसी मज़दूर को दबाकर रखें।',
        'No Workers Found': 'कोई मज़दूर नहीं मिला',
        'No workers match your search criteria. Try adjusting your filters.':
            'आपकी खोज से कोई मज़दूर नहीं मिला। छाँटने का तरीक़ा बदलकर देखें।',
        'Start by adding your first worker to the system.':
            'शुरू करने के लिए पहला मज़दूर जोड़ें।',
        'Add First Worker': 'पहला मज़दूर जोड़ें',
        'Search by name, ID, or phone...': 'नाम, आईडी या फ़ोन से खोजें...',
        'Worker list pages': 'मज़दूरों की सूची के पन्ने',

        # --- payroll --------------------------------------------------------
        'Gross Payroll': 'कुल वेतन',
        'Total Deductions': 'कुल कटौती',
        'paid': 'दे दिया',
        'pending': 'बाक़ी',
        'Generate / Refresh Payroll': 'वेतन बनाएँ / ताज़ा करें',
        'Saves the latest calculation for every active worker this month. '
        'Months already marked Paid are left untouched.':
            'इस महीने के हर चालू मज़दूर का ताज़ा हिसाब सेव करता है। '
            'जिन महीनों पर “दे दिया” लगा है, उन्हें नहीं छेड़ा जाता।',
        'Preview before generating': 'बनाने से पहले देखें',
        'No active workers found.': 'कोई चालू मज़दूर नहीं है।',
        'Not Saved': 'सेव नहीं',
        'Gross': 'कुल',
        'Export CSV': 'CSV निकालें',
        'Download Excel': 'एक्सेल डाउनलोड करें',
        'Deduct.': 'कटौती',
        'Mark Pending': 'बाक़ी लगाएँ',
        'Mark Paid': 'दे दिया लगाएँ',
        'Generate to enable': 'पहले वेतन बनाएँ',
        'Press and hold a worker to run payroll for several at once.':
            'एक साथ कई का वेतन बनाने के लिए किसी मज़दूर को दबाकर रखें।',

        # --- transactions ---------------------------------------------------
        'Advances, Loans, Bonuses & Deductions': 'पेशगी, क़र्ज़, इनाम और कटौती',
        'All workers': 'सभी मज़दूर',
        'Extra Payments': 'अतिरिक्त भुगतान',
        'Advances / Deductions': 'पेशगी / कटौती',
        'Cancelled': 'रद्द',
        'Press and hold a transaction to select several at once.':
            'एक साथ कई चुनने के लिए किसी लेन-देन को दबाकर रखें।',
        'No Transactions': 'कोई लेन-देन नहीं',
        'Add Transaction': 'लेन-देन जोड़ें',
        'Payroll updates automatically': 'वेतन अपने-आप बदल जाएगा',
        'All transactions automatically update': 'सभी लेन-देन अपने-आप',
        'payroll — extra payments are added, advances and deductions are '
        'recovered from net pay.':
            'के वेतन में जुड़ जाते हैं — अतिरिक्त भुगतान जोड़ा जाता है, और '
            'पेशगी तथा कटौती देने योग्य रक़म से काट ली जाती है।',
        'Select worker…': 'मज़दूर चुनें…',
        'Type': 'किस्म',
        'Date': 'तारीख़',
        'Notes': 'टिप्पणी',
        '(optional)': '(ज़रूरी नहीं)',
        'Cancel / Restore': 'रद्द करें / वापस लाएँ',

        # --- profile --------------------------------------------------------
        'Account Settings': 'खाते की सेटिंग',
        'Account': 'खाता',
        'Remove photo': 'फ़ोटो हटाएँ',
        'Account Information': 'खाते की जानकारी',
        'Email': 'ईमेल',
        'Role': 'भूमिका',
        'Mobile': 'मोबाइल',
        'Member Since': 'कब से',
        'Permissions': 'अनुमतियाँ',
        'Edit Profile': 'प्रोफ़ाइल बदलें',
        'Change Password': 'पासवर्ड बदलें',
        'Manage Workers': 'मज़दूर देखें',
        'Export Data': 'डेटा निकालें',
        'System Information': 'सिस्टम की जानकारी',
        'Application': 'ऐप',
        'Database Status': 'डेटाबेस',
        'Connected': 'जुड़ा हुआ',
        'Last Backup': 'पिछला बैकअप',
        'Update your account information': 'अपने खाते की जानकारी बदलें',
        'Save Changes': 'बदलाव सेव करें',
        'Update your account password': 'अपने खाते का पासवर्ड बदलें',
        'Current Password': 'मौजूदा पासवर्ड',
        'New Password': 'नया पासवर्ड',
        'Confirm New Password': 'नया पासवर्ड दोबारा',
        'Update Password': 'पासवर्ड बदलें',

        # --- QR scanner -----------------------------------------------------
        "Scan a worker's ID card to mark attendance":
            'हाज़िरी लगाने के लिए मज़दूर का आईडी कार्ड स्कैन करें',
        'Open': 'खोलें',
        'Starting camera…': 'कैमरा चालू हो रहा है…',
        'Point the camera at the QR code on the ID card.':
            'कैमरे को आईडी कार्ड के QR कोड पर रखें।',
        'Flip camera': 'कैमरा बदलें',
        'Pause': 'रोकें',
        'Enter Employee ID': 'मज़दूर की आईडी डालें',
        'Check in': 'हाज़िरी लगाएँ',
        'Open full profile': 'पूरी प्रोफ़ाइल खोलें',
        'Camera unavailable': 'कैमरा उपलब्ध नहीं',

        # The scanner's own notices. These are raised in JavaScript, so they
        # never pass through the flash filter or the JSON translator — the
        # template hands them over already translated, via _()|tojson.
        'Scanner unavailable': 'स्कैनर उपलब्ध नहीं',
        # The scanned card: the line under the worker's name, and the label
        # on the green button.
        'Today: %s': 'आज: %s',
        'in %s': 'आए %s',
        'out %s': 'गए %s',
        # 'shift open' is already in the table further up, for the same
        # meaning on another screen — one wording, not two.
        'Not marked today yet': 'आज अभी हाज़िरी नहीं लगी',
        'Closure day: %s — attendance is locked.':
            'छुट्टी का दिन: %s — हाज़िरी बंद है।',
        # Mirrors 'Check in' ('हाज़िरी लगाएँ') and uses the same word for a
        # departure the rest of the app does: जाने का समय.
        'Check out': 'जाने का समय लगाएँ',
        'Shift closed': 'शिफ़्ट पूरी हुई',
        'Site: %s': 'साइट: %s',
        'Project: %s': 'प्रोजेक्ट: %s',
        "Couldn't load the scanner. Check your connection, or enter the "
        'Employee ID below.':
            'स्कैनर चालू नहीं हो सका। कनेक्शन देखें, या नीचे मज़दूर की आईडी डालें।',
        'Scanner paused': 'स्कैनर रुका हुआ है',
        'Scanner paused — tap Resume to scan again.':
            'स्कैनर रुका हुआ है — दोबारा स्कैन करने के लिए “चालू करें” दबाएँ।',
        'Resume': 'चालू करें',
        'Looking up %s…': '%s देख रहे हैं…',
        'No matching worker.': 'इस आईडी का कोई मज़दूर नहीं मिला।',
        'Enter or scan an employee ID.': 'मज़दूर की आईडी डालें या स्कैन करें।',
        # The running account: what a worker has earned, what they have
        # drawn, and what is still theirs.
        'Still owed': 'अभी बाक़ी है',
        # The itemised money on a payslip.
        'Recorded by': 'दर्ज किया',
        'Total taken this month': 'इस महीने कुल लिया',
        'Total added this month': 'इस महीने कुल जुड़ा',
        'Taken': 'लिया',
        'Settled': 'चुका दिया',
        'Not paid': 'अभी नहीं दिया',
        'Brought forward': 'पिछला बाक़ी',
        'Carried forward': 'आगे बाक़ी',
        'Taken during the month': 'इस महीने लिया',
        'Wages paid out': 'मज़दूरी दी गई',
        'Open payslip': 'पर्ची खोलें',
        'Account & dues': 'हिसाब और बाक़ी',
        'Earned, taken and still owed, month by month':
            'हर महीने का कमाया, लिया और बाक़ी',
        'Nothing to show yet — this worker has no completed month.':
            'अभी कुछ नहीं है — इस मज़दूर का कोई पूरा महीना नहीं हुआ।',
        # Whether uploaded photos will still be there tomorrow.
        'Uploaded photos are not being kept':
            'अपलोड की गई तस्वीरें सेव नहीं हो रही हैं',
        "Worker photos and the company logo are being written to this "
        "server's temporary disk. They show now, and disappear the next "
        'time the app restarts or is updated. To keep them, set '
        'SUPABASE_URL and SUPABASE_SERVICE_KEY in the hosting '
        'environment and upload the photos again.':
            'मज़दूरों की तस्वीरें और कंपनी का लोगो इस सर्वर की अस्थायी डिस्क पर '
            'लिखे जा रहे हैं। अभी दिखते हैं, पर ऐप के दोबारा चालू होते ही या '
            'अपडेट होते ही मिट जाएँगे। इन्हें बनाए रखने के लिए होस्टिंग में '
            'SUPABASE_URL और SUPABASE_SERVICE_KEY सेट करें और तस्वीरें दोबारा '
            'अपलोड करें।',
        'Photos are stored permanently.':
            'तस्वीरें हमेशा के लिए सेव हो रही हैं।',
        # The attendance day view paints its own markup too; these two were
        # the last English left in it.
        'Close day detail': 'दिन की जानकारी बंद करें',
        'Select a date to see its detail.':
            'जानकारी देखने के लिए कोई तारीख़ चुनें।',
        'No matching worker on your site. Check the ID or contact the '
        'Administrator.':
            'आपकी साइट पर इस आईडी का कोई मज़दूर नहीं है। आईडी देखें या एडमिन '
            'से कहें।',
        'No connection — check your internet and try again, or mark '
        'attendance from the Attendance screen.':
            'कनेक्शन नहीं है — इंटरनेट देखकर दोबारा कोशिश करें, या हाज़िरी '
            'वाली स्क्रीन से हाज़िरी लगाएँ।',
        'The server returned an unexpected response. Please try again.':
            'सर्वर से अनपेक्षित जवाब आया। दोबारा कोशिश करें।',
        'Attendance updated.': 'हाज़िरी दर्ज हो गई।',
        'Could not update attendance.': 'हाज़िरी दर्ज नहीं हो सकी।',
        'Could not save attendance. Please try again.':
            'हाज़िरी सेव नहीं हुई। दोबारा कोशिश करें।',
        'No connection — attendance was not saved.':
            'कनेक्शन नहीं है — हाज़िरी सेव नहीं हुई।',
        'Amount must be greater than zero.': 'रक़म शून्य से ज़्यादा होनी चाहिए।',
        'Could not record the payment. Please try again.':
            'रक़म दर्ज नहीं हो सकी। दोबारा कोशिश करें।',
        'No connection — the payment was not recorded.':
            'कनेक्शन नहीं है — रक़म दर्ज नहीं हुई।',

        # --- closure days ---------------------------------------------------
        'Closure Days': 'छुट्टी के दिन',
        'Holidays & Scheduled Closures': 'त्योहार और तय छुट्टियाँ',
        'Add Closure Date': 'छुट्टी की तारीख़ जोड़ें',
        'Closure Reason/Remark': 'छुट्टी की वजह',
        'Applies To': 'किन पर लागू',
        'Allow attendance if worker present':
            'मज़दूर आ जाए तो हाज़िरी लगने दें',
        'Scheduled Closures': 'तय छुट्टियाँ',
        'No closure days configured yet.': 'अभी कोई छुट्टी का दिन तय नहीं है।',
        'upcoming': 'आगे',

        # --- assignments ----------------------------------------------------
        'Assign & transfer workers to sites, projects, tasks':
            'मज़दूरों को साइट, प्रोजेक्ट और काम पर लगाएँ या बदलें',
        'All': 'सभी',
        'Assigned': 'लगे हुए',
        'Unassigned': 'कहीं नहीं लगे',
        'Not assigned': 'कहीं नहीं लगे',
        'Assign': 'लगाएँ',
        'Transfer': 'बदलें',
        'End': 'हटाएँ',
        'All sites': 'सभी साइट',
        'All projects': 'सभी प्रोजेक्ट',
        'Assign selected workers': 'चुने हुए मज़दूरों को लगाएँ',
        'Press and hold a worker to assign or end several at once.':
            'एक साथ कई को लगाने या हटाने के लिए किसी मज़दूर को दबाकर रखें।',

        # --- profile roles and permissions ----------------------------------
        'Admin Account': 'एडमिन खाता',
        'System Administrator': 'सिस्टम एडमिन',
        'Manage workers & payroll': 'मज़दूर और वेतन देखें',
        'Mark and edit attendance': 'हाज़िरी लगाएँ और बदलें',
        'Company settings & closures': 'कंपनी सेटिंग और छुट्टियाँ',
        'Transactions & reports': 'लेन-देन और रिपोर्ट',
        'Manage attendance users': 'हाज़िरी वाले यूज़र देखें',

        # --- settings -------------------------------------------------------
        'Company, Sites, Projects & Users': 'कंपनी, साइट, प्रोजेक्ट और यूज़र',
        'Depts': 'विभाग',
        'Users': 'यूज़र',
        'Company Logo': 'कंपनी का लोगो',
        'Company Name': 'कंपनी का नाम',
        'Website': 'वेबसाइट',
        'Save Company Settings': 'कंपनी सेटिंग सेव करें',
        'Shown automatically on worker PDFs, payroll slips, salary reports '
        'and attendance reports.':
            'मज़दूर की PDF, तनख़्वाह पर्ची, वेतन रिपोर्ट और हाज़िरी रिपोर्ट '
            'पर अपने-आप छपता है।',
        'Press and hold any item above to select several at once.':
            'ऊपर किसी भी चीज़ को दबाकर रखें और एक साथ कई चुनें।',
        'Company Details': 'कंपनी की जानकारी',
        'Company': 'कंपनी',
        'Address': 'पता',
        'Departments': 'विभाग',
        'Sites': 'साइट',
        'Projects': 'प्रोजेक्ट',
        'Tasks': 'काम',
        'Add': 'जोड़ें',
        'Salary & Attendance Rules': 'तनख़्वाह और हाज़िरी के नियम',
        'Working days in a month': 'महीने में काम के दिन',
        'Rounding': 'पूर्णांकन',
        'Paid leave per month': 'महीने की मिलने वाली छुट्टी',
        'Deduct for absence': 'ग़ैरहाज़िरी पर कटौती',

        # --- the rest of the interface -----------------------------------
        # The screens a mukadam uses every day were translated first and
        # the deep administrative ones were not, which left a Hindi
        # settings screen reading mostly in English. These are those.
        '% of project rate / day': 'प्रोजेक्ट रेट का % / दिन',
        'Absence Policy': 'ग़ैरहाज़िरी का नियम',
        'Absent Days': 'ग़ैरहाज़िर दिन',
        'Accrued': 'जमा',
        'Actual Hours Worked + %': 'असल में किए घंटे + %',
        'Actual Minutes Worked + %': 'असल में किए मिनट + %',
        'Actual calendar days (28/29/30/31)': 'असली कैलेंडर दिन (28/29/30/31)',
        'Add / Edit Project': 'प्रोजेक्ट जोड़ें / बदलें',
        'Add / Edit Site': 'साइट जोड़ें / बदलें',
        'Add / Edit Task': 'काम जोड़ें / बदलें',
        'Add Department': 'विभाग जोड़ें',
        'Add workers to start marking attendance.':
            'हाज़िरी लगाना शुरू करने के लिए मज़दूर जोड़ें।',
        'Additional Percentage (%)': 'अतिरिक्त प्रतिशत (%)',
        'Address (optional)': 'पता (ज़रूरी नहीं)',
        'Adjust': 'बदलें',
        'Adjust Attendance': 'हाज़िरी बदलें',
        'Adjust Leave Balance': 'छुट्टी का हिसाब बदलें',
        'Administration': 'प्रशासन',
        'All changes are recorded permanently': 'हर बदलाव हमेशा के लिए दर्ज होता है',
        'All markers': 'सभी दर्ज करने वाले',
        'Allowed Leaves per Month': 'महीने में मिलने वाली छुट्टी',
        'Allowed Leaves/Month': 'महीने में मिलने वाली छुट्टी',
        'Amount deducted for each extra leave day':
            'हर अतिरिक्त छुट्टी के दिन पर कटने वाली रक़म',
        'Any active assignment they already have is closed and replaced.':
            'उनकी कोई भी चालू नियुक्ति बंद करके नई लगा दी जाएगी।',
        'Applies to all three methods above': 'ऊपर के तीनों तरीक़ों पर लागू',
        'Apply Late Fine': 'देर से आने पर जुर्माना लगाएँ',
        'Apply Leave Policy': 'छुट्टी का नियम लागू करें',
        'Apply Overtime': 'ओवरटाइम लागू करें',
        'Archive/Restore': 'संग्रह / वापस लाएँ',
        'Archived': 'संग्रह में',
        'Assign Worker': 'मज़दूर को नियुक्त करें',
        'Assigned Projects': 'दिए गए प्रोजेक्ट',
        'Assigned Sites': 'दी गई साइटें',
        'At least 8 characters': 'कम से कम 8 अक्षर',
        'Attendance activity from all sites': 'सभी साइटों की हाज़िरी गतिविधि',
        'Attendance allowed if present': 'आने पर हाज़िरी लग सकती है',
        'Attendance list pages': 'हाज़िरी सूची के पन्ने',
        'Selected':
            'चुना गया',
        'Tap the camera to add one. The employee ID and QR code are made when you save.':
            'जोड़ने के लिए कैमरा दबाएँ। मज़दूर आईडी और QR कोड सेव करने पर बनते हैं।',
        'Tap the camera to replace the photo':
            'फ़ोटो बदलने के लिए कैमरा दबाएँ',
        'Custom Closure Days': 'बंदी के दिन',
        'Login': 'लॉगिन',
        'Register': 'खाता बनाएँ',
        'Set New Password': 'नया पासवर्ड सेट करें',
        'Welcome': 'स्वागत है',
        '0 selected':
            '0 चुने गए',
        '7 days free, then ₹29/month or ₹319/year':
            '7 दिन मुफ़्त, फिर ₹29 महीना या ₹319 साल',
        'Activate':
            'चालू करें',
        'Amount (₹)':
            'रक़म (₹)',
        # The scanner's payment section: an advance booked at the gate, on
        # the same card that marks the worker present.
        'Payment':
            'भुगतान',
        'Record payment':
            'भुगतान दर्ज करें',
        'Note (optional)':
            'टिप्पणी (ज़रूरी नहीं)',
        'Deducted from pay':
            'तनख़्वाह से कटेगा',
        'Added to pay':
            'तनख़्वाह में जुड़ेगा',
        'Assign / Transfer':
            'नियुक्त करें / तबादला',
        'Auto-Generated':
            'अपने आप बनेगा',
        'Deactivate':
            'बंद करें',
        'Deactivate Worker':
            'मज़दूर को बंद करें',
        'Half-Day on Closure Day':
            'बंदी के दिन आधा दिन',
        'Half-day rate remains active for this many minutes after half-shift time.':
            'आधी शिफ़्ट के बाद इतने मिनट तक आधे दिन का रेट चलता है।',
        'If the worker already has an active assignment, it is closed automatically as a transfer the day before the new start date.':
            'अगर मज़दूर की कोई नियुक्ति पहले से चालू है, तो वह नई तारीख़ से एक दिन पहले तबादले के तौर पर अपने आप बंद हो जाती है।',
        "Late minutes and overtime are recalculated automatically from the worker's shift settings.":
            'देर के मिनट और ओवरटाइम मज़दूर की शिफ़्ट सेटिंग से अपने आप दोबारा गिने जाते हैं।',
        'Mark as inactive — keeps all records':
            'बंद के तौर पर दर्ज करें — सारे रिकॉर्ड रहेंगे',
        'New Daily Salary / Rate (₹)':
            'नई दिहाड़ी / रेट (₹)',
        'No modifications yet. Promotions, salary changes and category changes are logged here permanently.':
            'अभी कोई बदलाव नहीं। पदोन्नति, तनख़्वाह और श्रेणी के बदलाव यहाँ हमेशा के लिए दर्ज होते हैं।',
        'These users log in with their mobile number. They can only mark attendance, scan QR codes and view workers on their assigned sites — nothing else.':
            'ये उपयोगकर्ता अपने मोबाइल नंबर से लॉगिन करते हैं। ये सिर्फ़ हाज़िरी लगा सकते हैं, QR स्कैन कर सकते हैं और अपनी दी गई साइटों के मज़दूर देख सकते हैं — इसके अलावा कुछ नहीं।',
        'permanent':
            'पक्का',
        'Attendance marked by site users will appear here.':
            'साइट के उपयोगकर्ताओं की लगाई हाज़िरी यहाँ दिखेगी।',
        'Authorized Attendance Users': 'हाज़िरी के अधिकार वाले उपयोगकर्ता',
        'Available': 'बाक़ी',
        'Base Wage': 'मूल मज़दूरी',
        'Basic Details': 'बुनियादी जानकारी',
        'Blank = deduct at the rounded daily salary.':
            'ख़ाली = पूर्णांकित दिहाड़ी के हिसाब से कटौती।',
        'Built For Daily Operations': 'रोज़ के काम के लिए बना',
        'Business Name': 'कंपनी का नाम',
        'Carry unused leave forward': 'बची छुट्टी आगे ले जाएँ',
        'Category (optional)': 'श्रेणी (ज़रूरी नहीं)',
        'Changed': 'बदला',
        'Check-in': 'आना',
        'Check-out': 'जाना',
        'Choose a strong password for your account':
            'अपने खाते के लिए मज़बूत पासवर्ड चुनें',
        'Cleaning': 'सफ़ाई',
        'Closure Bonus': 'बंदी का इनाम',
        'Closure Day Calculation Basis': 'बंदी के दिन के हिसाब का आधार',
        'Closure Day Payment': 'बंदी के दिन का भुगतान',
        'Closure Days Attended': 'बंदी के दिन जिनमें काम हुआ',
        'Closure bonus': 'बंदी का इनाम',
        'Cloud Sync': 'क्लाउड सिंक',
        'Company-wide': 'पूरी कंपनी में',
        'Completion date': 'पूरा होने की तारीख़',
        'Confirm Password': 'पासवर्ड दोबारा',
        'Confirm your password': 'अपना पासवर्ड दोबारा डालें',
        'Construction': 'निर्माण',
        'Contact person': 'संपर्क व्यक्ति',
        'Contact phone': 'संपर्क फ़ोन',
        'Contract': 'ठेके पर',
        'Covers approved leave first, then absences.':
            'पहले मंज़ूर छुट्टी, फिर ग़ैरहाज़िरी में गिनी जाती है।',
        'Create Your Account': 'अपना खाता बनाएँ',
        'Create a strong password': 'मज़बूत पासवर्ड बनाएँ',
        'Credit or debit accumulated leave days': 'जमा छुट्टी के दिन जोड़ें या घटाएँ',
        'Current assignment will be closed as a transfer':
            'मौजूदा नियुक्ति तबादले के तौर पर बंद होगी',
        'Daily progress and trend visibility': 'रोज़ की प्रगति और रुझान दिखते हैं',
        'Daily salary rounding': 'दिहाड़ी का पूर्णांकन',
        'Days (+ credit / − debit)': 'दिन (+ जोड़ें / − घटाएँ)',
        'Days Marked': 'दर्ज किए दिन',
        'Days Present': 'हाज़िर दिन',
        'Days before the joining date are never paid or deducted.':
            'भर्ती से पहले के दिनों का न पैसा मिलता है न कटौती होती है।',
        'Days worked during closure — bonus earned': 'बंदी में किए गए दिन — कमाया हुआ इनाम',
        'Deadline': 'आख़िरी तारीख़',
        'Deduct for unpaid absences': 'बिना तनख़्वाह ग़ैरहाज़िरी पर कटौती',
        'Deduction per day (blank = daily salary)': 'रोज़ की कटौती (ख़ाली = दिहाड़ी)',
        'Deduction rate per day': 'रोज़ की कटौती का रेट',
        'Delay Penalty (project-based workers)': 'देरी का जुर्माना (प्रोजेक्ट वाले मज़दूर)',
        'Delete Worker': 'मज़दूर हटाएँ',
        'Department name': 'विभाग का नाम',
        'Description (optional)': 'ब्योरा (ज़रूरी नहीं)',
        'Detailed Statistics': 'विस्तृत आँकड़े',
        'Effective Date': 'लागू होने की तारीख़',
        'Eligible days': 'गिने जाने वाले दिन',
        'Email (Optional)': 'ईमेल (ज़रूरी नहीं)',
        'Email Address': 'ईमेल पता',
        'Emergency Closure': 'आपात बंदी',
        'Employee Information': 'मज़दूर की जानकारी',
        'Employee Type': 'मज़दूर का प्रकार',
        'Enable extra pay when a worker is present on a closure/holiday day':
            'बंदी या छुट्टी के दिन काम करने पर अतिरिक्त रक़म चालू करें',
        'Enable/Disable': 'चालू / बंद',
        'End Time': 'ख़त्म होने का समय',
        'End date': 'ख़त्म होने की तारीख़',
        'Enter mobile number': 'मोबाइल नंबर डालें',
        'Enter your account email': 'अपने खाते का ईमेल डालें',
        'Enter your business name': 'अपनी कंपनी का नाम डालें',
        'Enter your email': 'अपना ईमेल डालें',
        'Enter your full name': 'अपना पूरा नाम डालें',
        'Entire company': 'पूरी कंपनी',
        'Estimated Net Pay': 'अनुमानित मिलने वाली रक़म',
        'Extra Leave / Leave Adjustment': 'अतिरिक्त छुट्टी / छुट्टी में बदलाव',
        'Extra Leave Days': 'अतिरिक्त छुट्टी के दिन',
        'Factory': 'कारख़ाना',
        'Fast Setup': 'तेज़ सेटअप',
        'Fixed % on Daily Rate': 'दिहाड़ी पर तय %',
        'Fixed amount for the project cycle.': 'प्रोजेक्ट के पूरे चक्र की तय रक़म।',
        'Fixed number of days': 'तय संख्या में दिन',
        'Fixed ₹ / delayed day': 'तय ₹ / देरी के दिन',
        'Flat bonus on top of full-day salary': 'पूरे दिन की तनख़्वाह के ऊपर सीधा इनाम',
        'Forgot Password': 'पासवर्ड भूल गए',
        'Full Time': 'पूरा समय',
        'Full name': 'पूरा नाम',
        'GST No.': 'जीएसटी नं.',
        'Half Day Grace Window (Minutes)': 'आधे दिन की छूट (मिनट)',
        'Half Day Rate': 'आधे दिन का रेट',
        'Half day payment amount': 'आधे दिन के भुगतान की रक़म',
        'Half-Day Grace': 'आधे दिन की छूट',
        'Half-day rate remains active for this many minutes after half-shift time':
            'आधी शिफ़्ट के बाद इतने मिनट तक आधे दिन का रेट चलता है',
        'Hourly Wage': 'घंटे की मज़दूरी',
        'Hours logged × hourly rate × (1 + %)': 'दर्ज घंटे × घंटे का रेट × (1 + %)',
        'ID Card': 'पहचान पत्र',
        'Individual project': 'एक प्रोजेक्ट',
        'Individual site': 'एक साइट',
        'Join Date': 'भर्ती की तारीख़',
        'Join the smart way to manage attendance':
            'हाज़िरी संभालने का समझदार तरीक़ा अपनाएँ',
        'Late Days': 'देर वाले दिन',
        'Late Deduction/Day': 'देर पर रोज़ की कटौती',
        'Late Fine Rate': 'देर के जुर्माने का रेट',
        'Late Policy': 'देर से आने का नियम',
        'Late Policy Deductions': 'देर से आने पर कटौती',
        'Late minutes and overtime are recalculated automatically from the worker’s shift.':
            'देर के मिनट और ओवरटाइम मज़दूर की शिफ़्ट से अपने आप दोबारा गिने जाते हैं।',
        'Leave Days (+ credit / − debit)': 'छुट्टी के दिन (+ जोड़ें / − घटाएँ)',
        'Leave Deduction per Day': 'छुट्टी पर रोज़ की कटौती',
        'Leave Deduction/Day': 'छुट्टी पर रोज़ की कटौती',
        'Leave Policy': 'छुट्टी का नियम',
        'Leave Policy Deductions': 'छुट्टी के नियम से कटौती',
        'Leave Type': 'छुट्टी का प्रकार',
        'Leave allowance (days per month)': 'महीने में मिलने वाली छुट्टी (दिन)',
        'Leave blank to use the daily salary': 'दिहाड़ी इस्तेमाल करने के लिए ख़ाली छोड़ें',
        'Leave days per month': 'महीने में छुट्टी के दिन',
        'Live Insights': 'लाइव जानकारी',
        'Live Reports': 'लाइव रिपोर्ट',
        'Loading day…': 'दिन लोड हो रहा है…',
        'Locked': 'बंद',
        'Logo': 'लोगो',
        'Made For Every Worksite': 'हर साइट के लिए बना',
        'Manage': 'संभालें',
        'Manage sites & projects': 'साइट और प्रोजेक्ट संभालें',
        'Mark all read': 'सब पढ़ा हुआ चिह्नित करें',
        'Minutes logged × minute rate × (1 + %)': 'दर्ज मिनट × मिनट का रेट × (1 + %)',
        'Mobile Number': 'मोबाइल नंबर',
        'Mobile number (login ID)': 'मोबाइल नंबर (लॉगिन आईडी)',
        'Mobile number verification is required before signup.':
            'खाता बनाने से पहले मोबाइल नंबर की पुष्टि ज़रूरी है।',
        'Modification History': 'बदलाव का इतिहास',
        'Modification Type': 'बदलाव का प्रकार',
        'Modify Worker': 'मज़दूर में बदलाव',
        'Monthly Summary': 'महीने का सारांश',
        'Monthly Working Days': 'महीने में काम के दिन',
        'Monthly salary basis': 'महीने की तनख़्वाह का आधार',
        'National': 'राष्ट्रीय',
        'Net payable': 'देने योग्य रक़म',
        'New': 'नया',
        'New Designation': 'नया पद',
        'No Notifications': 'कोई सूचना नहीं',
        'No Work, No Pay': 'काम नहीं तो पैसा नहीं',
        'No attendance allowed': 'हाज़िरी नहीं लग सकती',
        'No attendance users yet.': 'अभी कोई हाज़िरी वाला उपयोगकर्ता नहीं।',
        'No change': 'कोई बदलाव नहीं',
        'No departments yet. Worker forms also accept free-text departments.':
            'अभी कोई विभाग नहीं। मज़दूर के फ़ॉर्म में विभाग सीधे लिखा भी जा सकता है।',
        'No modifications yet. Promotions, salary changes and category changes are recorded here.':
            'अभी कोई बदलाव नहीं। पदोन्नति, तनख़्वाह और श्रेणी के बदलाव यहाँ दर्ज होते हैं।',
        'No penalty': 'कोई जुर्माना नहीं',
        'No projects available — add projects in Settings':
            'कोई प्रोजेक्ट नहीं — सेटिंग में प्रोजेक्ट जोड़ें',
        'No projects yet. Add your first project above.':
            'अभी कोई प्रोजेक्ट नहीं। ऊपर अपना पहला प्रोजेक्ट जोड़ें।',
        'No projects yet. Empty = all projects.':
            'अभी कोई प्रोजेक्ट नहीं। ख़ाली = सभी प्रोजेक्ट।',
        'No sites available — add sites first. Empty = all sites.':
            'कोई साइट नहीं — पहले साइट जोड़ें। ख़ाली = सभी साइटें।',
        'No sites available — add sites in Settings':
            'कोई साइट नहीं — सेटिंग में साइट जोड़ें',
        'No sites yet. Add your first site above.':
            'अभी कोई साइट नहीं। ऊपर अपनी पहली साइट जोड़ें।',
        'No tasks yet. Add your first task above.':
            'अभी कोई काम नहीं। ऊपर अपना पहला काम जोड़ें।',
        'No transactions yet. Advances, loans and bonuses will appear here.':
            'अभी कोई लेन-देन नहीं। पेशगी, क़र्ज़ और इनाम यहाँ दिखेंगे।',
        'Not assigned to any project or site.': 'किसी प्रोजेक्ट या साइट पर नहीं लगे हैं।',
        'Note': 'नोट',
        'Number of leaves without salary deduction': 'बिना कटौती वाली छुट्टी की संख्या',
        'Office': 'दफ़्तर',
        'One-time Bonus': 'एकमुश्त इनाम',
        'Optional': 'ज़रूरी नहीं',
        'Other': 'अन्य',
        'Other Note': 'दूसरा नोट',
        'Override for this worker': 'इस मज़दूर के लिए अलग नियम',
        'Overtime Pay': 'ओवरटाइम की रक़म',
        'Overtime Rate': 'ओवरटाइम का रेट',
        'Overtime and late deductions included': 'ओवरटाइम और देर की कटौती शामिल',
        'Owner Name': 'मालिक का नाम',
        'PDF Report': 'PDF रिपोर्ट',
        'Paid monthly leave': 'महीने की तनख़्वाह वाली छुट्टी',
        'Part Time': 'आधा समय',
        'Password (leave blank to keep current)': 'पासवर्ड (वही रखने के लिए ख़ाली छोड़ें)',
        'Payment Information': 'भुगतान की जानकारी',
        'Payment Settings': 'भुगतान की सेटिंग',
        'Payroll Policies': 'वेतन के नियम',
        'Payroll Ready': 'वेतन के लिए तैयार',
        'Per Day': 'प्रतिदिन',
        'Per Hour': 'प्रति घंटा',
        'Per Minute': 'प्रति मिनट',
        'Permanent': 'पक्का',
        'Permanently remove — cannot be undone': 'हमेशा के लिए हटाएँ — वापस नहीं आएगा',
        'Personal Information': 'निजी जानकारी',
        'Position/Role': 'पद / काम',
        'Present + Late': 'हाज़िर + देर से',
        'Present Days': 'हाज़िर दिन',
        'Press and hold a closure day to select several at once.':
            'एक साथ कई चुनने के लिए किसी बंदी के दिन को दबाकर रखें।',
        'Press and hold a notification to select several at once.':
            'एक साथ कई चुनने के लिए किसी सूचना को दबाकर रखें।',
        'Privacy Policy': 'निजता नीति',
        'Profiles, roles, and contract details': 'प्रोफ़ाइल, पद और ठेके की जानकारी',
        'Project Amount': 'प्रोजेक्ट की रक़म',
        'Project Based': 'प्रोजेक्ट के हिसाब से',
        'Project Deadline': 'प्रोजेक्ट की आख़िरी तारीख़',
        'Project name': 'प्रोजेक्ट का नाम',
        'Promote': 'पदोन्नति',
        'Promotion (designation + salary)': 'पदोन्नति (पद + तनख़्वाह)',
        'QR Attendance': 'QR से हाज़िरी',
        'Quick and secure daily check-ins': 'तेज़ और सुरक्षित रोज़ाना हाज़िरी',
        'Re-enter password': 'पासवर्ड दोबारा डालें',
        'Reason': 'वजह',
        'Reason / details': 'वजह / ब्योरा',
        'Reason for adjustment': 'बदलाव की वजह',
        'Recent Attendance': 'हाल की हाज़िरी',
        'Recent Records': 'हाल के रिकॉर्ड',
        'Recent policy changes': 'हाल के नियम बदलाव',
        'Reg. No.': 'रजिस्ट्रेशन नं.',
        'Reset Your Password': 'अपना पासवर्ड बदलें',
        'Retail': 'दुकान',
        'Salary Calculation Policy': 'तनख़्वाह के हिसाब का नियम',
        'Salary Increment': 'तनख़्वाह में बढ़ोतरी',
        'Salary calculation method': 'तनख़्वाह का हिसाब लगाने का तरीक़ा',
        'Salary is divided by this to get a daily rate.':
            'तनख़्वाह को इससे भाग देकर दिहाड़ी निकलती है।',
        'Salary rules decide what people are paid, so every change is recorded.':
            'तनख़्वाह के नियम तय करते हैं कि किसे कितना मिलेगा, इसलिए हर बदलाव दर्ज होता है।',
        'Save Attendance User': 'हाज़िरी वाला उपयोगकर्ता सेव करें',
        'Save Project': 'प्रोजेक्ट सेव करें',
        'Save Site': 'साइट सेव करें',
        'Save Task': 'काम सेव करें',
        'Save override': 'अलग नियम सेव करें',
        'Search name or employee ID…': 'नाम या मज़दूर आईडी खोजें…',
        'Security': 'सुरक्षा',
        'Select Department': 'विभाग चुनें',
        'Select Pay Type': 'मज़दूरी का प्रकार चुनें',
        'Select Type': 'प्रकार चुनें',
        'Select all': 'सब चुनें',
        'Set a New Password': 'नया पासवर्ड सेट करें',
        'Site name': 'साइट का नाम',
        'Special Incentive': 'ख़ास प्रोत्साहन',
        'Standard Hours / Day': 'रोज़ के तय घंटे',
        'Start Date': 'शुरू होने की तारीख़',
        'Start Time': 'शुरू होने का समय',
        'Start Your Free Trial': 'मुफ़्त आज़माना शुरू करें',
        'Start date': 'शुरू होने की तारीख़',
        'Start managing attendance efficiently': 'हाज़िरी को बेहतर तरीक़े से संभालें',
        'Task name': 'काम का नाम',
        'Temporary': 'कच्चा',
        'Terms of Service': 'सेवा की शर्तें',
        'These users log in with their mobile number. They can only mark attendance.':
            'ये उपयोगकर्ता अपने मोबाइल नंबर से लॉगिन करते हैं। ये सिर्फ़ हाज़िरी लगा सकते हैं।',
        'This Month\'s Summary': 'इस महीने का सारांश',
        'Total Closure Bonus': 'बंदी का कुल इनाम',
        'Total Records': 'कुल रिकॉर्ड',
        'Total Working Days': 'कुल काम के दिन',
        'Total net payable': 'कुल देने योग्य रक़म',
        'Unlimited Workers': 'असीमित मज़दूर',
        'Unpaid': 'बिना भुगतान',
        'Unspecified': 'तय नहीं',
        'Update profile details': 'प्रोफ़ाइल की जानकारी बदलें',
        'Used to derive daily rate': 'दिहाड़ी निकालने के लिए',
        'Used to derive hourly rate': 'घंटे का रेट निकालने के लिए',
        'Used when worked time is up to 50% of shift hours.':
            'जब काम का समय शिफ़्ट के 50% तक हो तब लगता है।',
        'Value': 'रक़म',
        'View Details': 'ब्योरा देखें',
        'We\'ll email you a reset link': 'हम आपको ईमेल पर लिंक भेजेंगे',
        'Work Details': 'काम की जानकारी',
        'Work Information': 'काम की जानकारी',
        'Worker Photo': 'मज़दूर की फ़ोटो',
        'Worker Profile': 'मज़दूर की प्रोफ़ाइल',
        'Worker Records': 'मज़दूर के रिकॉर्ड',
        'Working Hours': 'काम के घंटे',
        'You are offline': 'आप ऑफ़लाइन हैं',
        'deducted': 'काटी गई',
        'e.g. 10 for 10%': 'जैसे 10% के लिए 10',
        'e.g. Approved extra leave': 'जैसे मंज़ूर की गई अतिरिक्त छुट्टी',
        'e.g. Senior Supervisor': 'जैसे वरिष्ठ सुपरवाइज़र',
        'e.g. Transferred for finishing work': 'जैसे फ़िनिशिंग के काम के लिए तबादला',
        'e.g., National Holiday, Festival, Company Event':
            'जैसे राष्ट्रीय छुट्टी, त्योहार, कंपनी का कार्यक्रम',
        'eligible days': 'गिने जाने वाले दिन',
        'per day': 'प्रतिदिन',
        '— No project —': '— कोई प्रोजेक्ट नहीं —',
        '— No site —': '— कोई साइट नहीं —',
        '— No task —': '— कोई काम नहीं —',
        '— None —': '— कोई नहीं —',
    },
}


#: Weekday and month names, because strftime only knows the server's C locale
#: and a date header reading "Tuesday, October 20" on an otherwise Hindi
#: screen is the single most visible place the translation gives up.
#: Weekdays are indexed by date.weekday() — Monday first.
WEEKDAYS = {
    'hi': ['सोमवार', 'मंगलवार', 'बुधवार', 'गुरुवार', 'शुक्रवार', 'शनिवार', 'रविवार'],
}
WEEKDAYS_SHORT = {
    'hi': ['सोम', 'मंगल', 'बुध', 'गुरु', 'शुक्र', 'शनि', 'रवि'],
}
MONTHS = {
    'hi': ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई',
           'अगस्त', 'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर'],
}
MONTHS_SHORT = {
    'hi': ['जन', 'फ़र', 'मार्च', 'अप्रै', 'मई', 'जून', 'जुल',
           'अग', 'सित', 'अक्तू', 'नव', 'दिस'],
}


def month_name(number, lang, short=False):
    """Month 1-12 in the interface language, English when there is none."""
    table = (MONTHS_SHORT if short else MONTHS).get(lang)
    if table and 1 <= number <= 12:
        return table[number - 1]
    return _ENGLISH_MONTHS[number - 1] if 1 <= number <= 12 else ''


def weekday_names(lang, short=False):
    """Monday-first weekday names, English if the language has none."""
    table = (WEEKDAYS_SHORT if short else WEEKDAYS).get(lang)
    if table:
        return list(table)
    if short:
        return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
            'Saturday', 'Sunday']


#: Word order differs, not just the words: "Tuesday, October 20, 2026" reads
#: as "20 अक्टूबर 2026, मंगलवार" in Hindi. Patterns not listed here keep the
#: English ordering with translated names, which is still readable.
DATE_PATTERNS = {
    'hi': {
        '%A, %B %d, %Y': '%d %B %Y, %A',
        '%B %d, %Y': '%d %B %Y',
    },
}


def format_date(value, fmt, lang):
    """strftime with localised day and month names.

    Only %A/%a/%B/%b are substituted; everything else is left to strftime, so
    an existing format string keeps working unchanged and an untranslated
    language comes out exactly as it does today.
    """
    if value is None:
        return ''
    if lang == DEFAULT_LANGUAGE or lang not in WEEKDAYS:
        return value.strftime(fmt)
    fmt = DATE_PATTERNS.get(lang, {}).get(fmt, fmt)
    repl = {
        '%A': WEEKDAYS[lang][value.weekday()],
        '%a': WEEKDAYS_SHORT[lang][value.weekday()],
        '%B': MONTHS[lang][value.month - 1],
        '%b': MONTHS_SHORT[lang][value.month - 1],
    }
    # Walk the format so a literal %% is never mistaken for a directive.
    out, i = [], 0
    while i < len(fmt):
        token = fmt[i:i + 2]
        if token in repl:
            out.append(repl[token])
            i += 2
        elif token == '%%':
            out.append('%%')
            i += 2
        else:
            out.append(fmt[i])
            i += 1
    return value.strftime(''.join(out))


#: The salary engine writes its working out as English prose and stores it in
#: the payroll snapshot, where it is the audit record — so it must not be
#: translated at the point it is generated, or a payslip would say different
#: things depending on who happened to open it. These patterns translate it on
#: the way to the screen instead, which also covers snapshots already saved.
#: Each entry is (compiled pattern, Hindi template using \1, \2…).
# These replacements put a ₹ in front of each amount, which is right for a
# note stored before salary.py wrote its own — and gives ₹₹38,000 for one
# written after. translate_note collapses the double, so both read properly
# and the stored audit records are left exactly as they were written.
_NOTE_PATTERNS_SOURCE = {
    'hi': [
        (r'^Joining date (.+?) falls after this period, so no salary is payable\.$',
         r'भर्ती की तारीख़ \1 इस अवधि के बाद है, इसलिए कोई तनख़्वाह नहीं बनती।'),
        (r'^Joined (.+?)\. Paid for (\S+) attended day\(s\) from the joining date at (\S+)/day\.$',
         r'\1 को भर्ती। भर्ती की तारीख़ से \2 दिन की हाज़िरी पर ₹\3 प्रतिदिन के हिसाब से भुगतान।'),
        (r'^Joined (.+?), so (\d+) of (\d+) day\(s\) are eligible: (\d+) x (\S+) = (\S+)\.$',
         r'\1 को भर्ती, इसलिए \3 में से \2 दिन गिने गए: \4 × ₹\5 = ₹\6।'),
        (r'^Daily rate (\S+) x (\d+) day\(s\) basis = (\S+)\.$',
         r'दिहाड़ी ₹\1 × \2 दिन = ₹\3।'),
        (r'^Full monthly salary (\S+) applies\.$',
         r'पूरी महीने की तनख़्वाह ₹\1 लागू है।'),
        (r'^Deduction: (\S+) day\(s\) x (\S+) = (\S+)\.$',
         r'कटौती: \1 दिन × ₹\2 = ₹\3।'),
        (r'^Paid leave allowance (\S+) day\(s\) covered (\S+) absence\(s\) and (\S+) leave\(s\)\.$',
         r'\1 दिन की मिलने वाली छुट्टी से \2 ग़ैरहाज़िरी और \3 छुट्टी भर गई।'),
        (r'^Absence deduction is switched off, so (\d+) absent day\(s\) were not charged\.$',
         r'ग़ैरहाज़िरी पर कटौती बंद है, इसलिए \1 ग़ैरहाज़िर दिन की कटौती नहीं हुई।'),
        (r'^(\d+) attendance record\(s\) before the joining date were ignored\.$',
         r'भर्ती से पहले की \1 हाज़िरी नहीं गिनी गई।'),
        (r'^Deductions exceeded the eligible salary; net floored at 0\.$',
         r'कटौती तनख़्वाह से ज़्यादा हो गई; देने योग्य रक़म 0 रखी गई।'),
        (r'^Final payable: (\S+) - (\S+) = (\S+)\.$',
         r'देने योग्य रक़म: ₹\1 − ₹\2 = ₹\3।'),
        # Notes added by the payroll route rather than the engine.
        (r'^No-work-no-pay applied for absent days\.$',
         r'ग़ैरहाज़िर दिनों की मज़दूरी नहीं जोड़ी गई।'),
        (r'^Hourly wage is based on check-in/check-out duration\.$',
         r'मज़दूरी आने-जाने के समय के हिसाब से लगी है।'),
        (r'^Overtime policy added extra pay\.$',
         r'ओवरटाइम के नियम से अतिरिक्त रक़म जुड़ी।'),
        (r'^Bonus/extra payment transactions added to pay\.$',
         r'इनाम और अतिरिक्त भुगतान रक़म में जोड़े गए।'),
        (r'^Advance/loan/deduction transactions recovered from pay\.$',
         r'पेशगी, क़र्ज़ और कटौती रक़म से वसूल की गई।'),
        (r'^Absent days are paid because no-work-no-pay is disabled\.$',
         r'“काम नहीं तो पैसा नहीं” बंद है, इसलिए ग़ैरहाज़िर दिनों का भी पैसा मिला।'),
        (r'^Project delay penalty applied\.$',
         r'प्रोजेक्ट देर से होने की कटौती लगी।'),
        (r'^Project rate is fixed for the period\.$',
         r'इस अवधि के लिए प्रोजेक्ट का रेट तय है।'),
    ],
}

_NOTE_PATTERNS = {
    lang: [(re.compile(pattern), repl) for pattern, repl in entries]
    for lang, entries in _NOTE_PATTERNS_SOURCE.items()
}


#: salary.describe() composes its values ("Fixed days (26)", "2 day(s) per
#: month"), so they cannot be looked up as whole strings. Same approach as
#: the notes above: match the shape, keep the numbers.
_POLICY_PATTERNS_SOURCE = {
    'hi': [
        (r'^Fixed days \((\d+)\)$', r'तय दिन (\1)'),
        (r'^(\S+) day\(s\) per month$', r'हर महीने \1 दिन'),
    ],
}

_POLICY_PATTERNS = {
    lang: [(re.compile(p), r) for p, r in entries]
    for lang, entries in _POLICY_PATTERNS_SOURCE.items()
}


def translate_policy(text, lang):
    """One value out of salary.describe(), translated for display.

    Falls back to translate(), so the plain values ('On', 'Off', 'Nearest
    rupee') come from the ordinary table and only the composed ones need a
    pattern. Anything unrecognised stays English rather than being mangled.
    """
    if text is None or lang == DEFAULT_LANGUAGE:
        return text
    text = str(text).strip()
    for pattern, repl in _POLICY_PATTERNS.get(lang, ()):
        new, count = pattern.subn(repl, text)
        if count:
            return new
    return translate(text, lang)


def translate_note(text, lang):
    """Translate one generated salary note, or return it unchanged.

    A note whose shape is not recognised — because the engine grew a new one —
    comes back in English rather than being dropped or mangled.
    """
    if not text or lang == DEFAULT_LANGUAGE:
        return text
    for pattern, repl in _NOTE_PATTERNS.get(lang, ()):
        new, count = pattern.subn(repl, text.strip())
        if count:
            # The replacement supplies a ₹ because a note stored before the
            # engine wrote its own has none. One written since arrives with
            # it already, so the two meet as ₹₹ — collapse it.
            return new.replace('₹₹', '₹')
    return text


def translate_notes(text, lang):
    """Translate a run of notes that were joined into one paragraph."""
    if not text or lang == DEFAULT_LANGUAGE:
        return text
    # Sentences end in '.' and the numbers inside them contain '.' too, so
    # split only where a full stop is followed by a space and a capital or a
    # digit — the shape every generated note starts with.
    parts = re.split(r'(?<=\.)\s+(?=[A-Z0-9])', text.strip())
    return ' '.join(translate_note(p, lang) for p in parts)



#: Flash messages. Translated where they are shown rather than where they are
#: raised, so none of the 105 flash() call sites had to change and a message
#: already in flight still comes out in the reader's language.
FLASH_MESSAGES = {
    'hi': {
        'Assignment does not belong to this worker.':
            'यह नियुक्ति इस मज़दूर की नहीं है।',
        'Assignment marked as completed.': 'नियुक्ति पूरी हुई के रूप में दर्ज।',
        'Attendance user deleted.': 'हाज़िरी वाला यूज़र हटा दिया गया।',
        'Choose a project and/or a site for the assignment.':
            'नियुक्ति के लिए प्रोजेक्ट और/या साइट चुनें।',
        'Closure day added successfully': 'छुट्टी का दिन जुड़ गया',
        'Closure day deleted successfully': 'छुट्टी का दिन हटा दिया गया',
        'Closure day updated successfully': 'छुट्टी का दिन बदल दिया गया',
        'Company settings saved. They will appear on all PDFs and reports.':
            'कंपनी सेटिंग सेव हो गई। ये सभी PDF और रिपोर्ट पर दिखेंगी।',
        'Could not upload the logo right now. Other settings were saved.':
            'लोगो अभी अपलोड नहीं हो सका। बाक़ी सेटिंग सेव हो गईं।',
        'Current password is incorrect': 'मौजूदा पासवर्ड ग़लत है',
        'Email already registered': 'यह ईमेल पहले से रजिस्टर्ड है',
        'Enter a valid closure date.': 'छुट्टी की सही तारीख़ डालें।',
        'Enter a valid joining date.': 'भर्ती की सही तारीख़ डालें।',
        'Full name is required for an attendance user.':
            'हाज़िरी वाले यूज़र का पूरा नाम ज़रूरी है।',
        'If an account exists for that email, a password reset link has been sent.':
            'अगर उस ईमेल पर खाता है, तो पासवर्ड बदलने का लिंक भेज दिया गया है।',
        'Invalid attendance date.': 'हाज़िरी की तारीख़ ग़लत है।',
        'Invalid attendance status.': 'हाज़िरी की हालत ग़लत है।',
        'Invalid username or password': 'यूज़रनेम या पासवर्ड ग़लत है',
        'Mobile number already registered': 'यह मोबाइल नंबर पहले से रजिस्टर्ड है',
        'Modification note recorded.': 'बदलाव की टिप्पणी दर्ज हो गई।',
        'New QR code generated successfully': 'नया QR कोड बन गया',
        'New passwords do not match': 'नए पासवर्ड आपस में नहीं मिलते',
        'Nothing to update — enter a new designation and/or salary.':
            'बदलने को कुछ नहीं — नया पद और/या तनख़्वाह डालें।',
        'Only attendance users can be deleted here.':
            'यहाँ सिर्फ़ हाज़िरी वाले यूज़र हटाए जा सकते हैं।',
        'Only attendance users can be edited here.':
            'यहाँ सिर्फ़ हाज़िरी वाले यूज़र बदले जा सकते हैं।',
        'Only attendance users can be managed here.':
            'यहाँ सिर्फ़ हाज़िरी वाले यूज़र संभाले जा सकते हैं।',
        'Password changed successfully': 'पासवर्ड बदल गया',
        'Password must be at least 6 characters long.':
            'पासवर्ड कम से कम 6 अक्षरों का होना चाहिए।',
        'Password must be at least 8 characters':
            'पासवर्ड कम से कम 8 अक्षरों का होना चाहिए',
        'Password must be at least 8 characters long':
            'पासवर्ड कम से कम 8 अक्षरों का होना चाहिए',
        'Passwords do not match': 'पासवर्ड आपस में नहीं मिलते',
        'Please choose a valid transaction type.': 'लेन-देन की सही किस्म चुनें।',
        'Please choose an image to upload.': 'अपलोड करने के लिए तस्वीर चुनें।',
        'Please contact the Administrator to make changes.':
            'बदलाव के लिए एडमिन से कहें।',
        'Please contact the Administrator to mark absences or leaves.':
            'ग़ैरहाज़िरी या छुट्टी लगाने के लिए एडमिन से कहें।',
        'Please enter a valid mobile number': 'सही मोबाइल नंबर डालें',
        'Please enter a valid mobile number for the attendance user.':
            'हाज़िरी वाले यूज़र का सही मोबाइल नंबर डालें।',
        'Please enter the number of leave days to credit or debit.':
            'कितने दिन की छुट्टी जोड़नी या घटानी है, वह डालें।',
        'Please enter the payment amount.': 'भुगतान की रक़म डालें।',
        'Please enter your full name': 'अपना पूरा नाम डालें',
        'Please enter the new salary amount.': 'नई तनख़्वाह की रक़म डालें।',
        'Please upload a valid logo image (JPG, JPEG, PNG, GIF, or WEBP).':
            'सही लोगो तस्वीर अपलोड करें (JPG, JPEG, PNG, GIF या WEBP)।',
        'Please verify your mobile number with OTP before registering':
            'रजिस्टर करने से पहले OTP से मोबाइल नंबर जाँच लें',
        'Profile photo removed.': 'प्रोफ़ाइल फ़ोटो हटा दी गई।',
        'Profile photo updated.': 'प्रोफ़ाइल फ़ोटो बदल दी गई।',
        'Profile updated successfully': 'प्रोफ़ाइल बदल गई',
        'Registration successful! Check your email to confirm your account, then log in.':
            'रजिस्ट्रेशन हो गया! ईमेल देखकर खाता पक्का करें, फिर लॉगिन करें।',
        'Registration successful! Please login using your email.':
            'रजिस्ट्रेशन हो गया! अपने ईमेल से लॉगिन करें।',
        'Salary calculation policy saved. Payroll already marked paid is not affected.':
            'तनख़्वाह के हिसाब का नियम सेव हो गया। जिस वेतन पर “दे दिया” लगा है, उस पर असर नहीं पड़ेगा।',
        'That date is in the future — attendance cannot be marked yet.':
            'यह तारीख़ आगे की है — अभी हाज़िरी नहीं लग सकती।',
        'This account has been disabled. Please contact the Administrator.':
            'यह खाता बंद कर दिया गया है। एडमिन से कहें।',
        'This mobile number is already registered to another account.':
            'यह मोबाइल नंबर किसी और खाते पर पहले से है।',
        'Transaction amount must be greater than zero.':
            'लेन-देन की रक़म शून्य से ज़्यादा होनी चाहिए।',
        'Transaction deleted permanently.': 'लेन-देन हमेशा के लिए हटा दिया गया।',
        # Confirming a payment, and part-settling a month
        'Receipt confirmed.': 'मिलने की पुष्टि दर्ज हो गई।',
        'That payment was already confirmed.':
            'उस भुगतान की पुष्टि पहले ही हो चुकी है।',
        'That entry was cancelled, so there is nothing to confirm.':
            'वह लेन-देन रद्द कर दिया गया था, पुष्टि करने के लिए कुछ नहीं है।',
        'Enter how much has been paid for this month.':
            'इस महीने का कितना दिया गया है, वह लिखें।',
        'A reference should be 3 to 60 letters, digits, - or / — the UTR or cheque number from the bank.':
            'संदर्भ 3 से 60 अक्षर, अंक, - या / का होना चाहिए — बैंक से मिला UTR '
            'या चेक नंबर।',
        'Choose how payments should be counted.':
            'चुनें कि भुगतान कैसे गिना जाए।',
        'A check-out needs a check-in time as well.':
            'जाने का समय दर्ज करने के लिए आने का समय भी चाहिए।',
        'Check-out must be later than check-in.':
            'जाने का समय आने के समय के बाद होना चाहिए।',
        'Choose a valid transaction type.': 'लेन-देन की सही किस्म चुनें।',
        # 'Amount must be greater than zero.' is in TRANSLATIONS instead: the
        # scanner raises it in JavaScript as well as receiving it from the
        # endpoint, and only that table is readable from a template's _().
        # translate_flash falls back to it, so the JSON path is unaffected.
        'That date is in the future.': 'यह तारीख़ आने वाले दिन की है।',
        'Closure not found for this date.': 'इस तारीख़ की कोई छुट्टी नहीं मिली।',
        'Closure removed.': 'छुट्टी हटा दी गई।',
        'A closure needs a reason.': 'छुट्टी की वजह लिखना ज़रूरी है।',
        'No open shifts to close.': 'बंद करने के लिए कोई खुली शिफ़्ट नहीं है।',
        'Unknown action.': 'यह काम पहचाना नहीं गया।',
        'Add a mobile number for this worker before creating a login.':
            'लॉगिन बनाने से पहले इस मज़दूर का मोबाइल नंबर डालें।',
        'That mobile number is already used by another login.':
            'यह मोबाइल नंबर किसी और लॉगिन पर पहले से है।',
        'Login removed.': 'लॉगिन हटा दिया गया।',
        'This worker had no login.': 'इस मज़दूर का कोई लॉगिन नहीं था।',
        'This login is not linked to a worker record. Please contact the Administrator.':
            'यह लॉगिन किसी मज़दूर से जुड़ा नहीं है। एडमिन से कहें।',
        'That worker is not on your list.': 'यह मज़दूर आपकी सूची में नहीं है।',
        'Powers saved.': 'अधिकार सेव हो गए।',
        'Create a login for this worker first.':
            'पहले इस मज़दूर का लॉगिन बनाएँ।',
        'Access Restricted': 'अनुमति नहीं है',
    },
}


def _hi_money(shape):
    """A money message whose first captured group is itself translatable.

    These messages begin with a transaction type — 'Advance Salary',
    'Refreshment Allowance' — which already has a Hindi name, the one the
    dropdown on the same screen shows. A plain replacement string would
    leave the English word sitting in the middle of a Hindi sentence, so the
    replacement is a function and the label is looked up. re.subn takes
    either. `shape` numbers its slots from the captured groups, so {0} is
    the translated label.
    """
    def repl(match):
        parts = list(match.groups())
        parts[0] = TRANSLATIONS['hi'].get(parts[0], parts[0])
        return shape.format(*parts)
    return repl


#: Flash messages that carry a value. Same approach as the salary notes:
#: match the shape, keep what was interpolated.
_FLASH_PATTERNS_SOURCE = {
    'hi': [
        # Notes the day view paints from JSON rather than raising as a flash.
        (r'^Payroll for (.+?) has already been generated\. '
         r'Re-generate it so this change is reflected in pay\.$',
         r'\1 का वेतन पहले ही बन चुका है। यह बदलाव पे में दिखे, '
         r'इसके लिए वेतन दोबारा बनाएँ।'),
        (r'^(.+?) had not joined on this date\.$',
         r'\1 इस तारीख़ को भर्ती नहीं हुए थे।'),
        (r'^Attendance is locked for (.+?) on this closure day\.$',
         r'इस छुट्टी के दिन \1 की हाज़िरी बंद है।'),
        (r'^Times updated for (.+?)\.$', r'\1 का समय बदल दिया गया।'),
        (r'^Closure added for (.+?)\.$', r'\1 के लिए छुट्टी जोड़ी गई।'),
        (r'^Login ready for (.+?)\. Username (\S+), password (\S+)\. '
         r'Write it down — it cannot be shown again\.$',
         r'\1 का लॉगिन तैयार। यूज़रनेम \2, पासवर्ड \3। '
         r'लिख लें — यह दोबारा नहीं दिखाया जाएगा।'),
        (r'^Attendance adjusted for (.+?)\.$', r'\1 की हाज़िरी बदल दी गई।'),
        (r'^Attendance is locked for (.+?) on this closure day \((.+?)\)\.$',
         r'इस छुट्टी के दिन (\2) \1 की हाज़िरी बंद है।'),
        (r'^Attendance is locked on this closure day \((.+?)\)\.$',
         r'इस छुट्टी के दिन (\1) हाज़िरी बंद है।'),
        (r'^Attendance user (.+?) saved\. They can log in with their mobile number\.$',
         r'हाज़िरी वाला यूज़र \1 सेव हो गया। वे अपने मोबाइल नंबर से लॉगिन कर सकते हैं।'),
        (r'^Bulk attendance marked as (.+?) for all workers$',
         r'सभी मज़दूरों की हाज़िरी “\1” लगा दी गई'),
        (r'^Cannot delete this (.+?) — it is referenced by (.+?)\. '
         r'Archive it instead to keep history intact\.$',
         r'यह \1 हटाया नहीं जा सकता — \2 इससे जुड़ा है। '
         r'इतिहास बचाए रखने के लिए इसे आर्काइव कर दें।'),
        (r'^Leave balance adjusted by (\S+) day\(s\) for (.+?)\.$',
         r'\2 की छुट्टी में \1 दिन का बदलाव किया गया।'),
        (r'^Promotion recorded for (.+?): (.+)$', r'\1 की तरक़्क़ी दर्ज: \2'),
        (r'^Salary policy saved for (.+?)\.$', r'\1 के लिए तनख़्वाह का नियम सेव हो गया।'),
        (r'^Salary updated for (.+?)\. Payroll recalculates automatically\.$',
         r'\1 की तनख़्वाह बदल दी गई। वेतन अपने-आप दोबारा जुड़ जाएगा।'),
        (r'^Transaction (.+?)\. Payroll updates automatically\.$',
         r'लेन-देन \1। वेतन अपने-आप बदल जाएगा।'),
        (r'^Worker (.+?) added successfully with ID: (.+)$',
         r'मज़दूर \1 जुड़ गया, आईडी: \2'),
        (r'^Worker (.+?) updated successfully$', r'मज़दूर \1 की जानकारी बदल गई'),
        # The scanner's two lookup failures, which carry a value.
        (r'^No worker found for ID (.+?)\.$',
         r'आईडी \1 का कोई मज़दूर नहीं मिला।'),
        # Only a worker is ever described this way today; the Hindi says so
        # ("no longer at work"), so a site or project worded the same later
        # wants its own shape rather than this one.
        (r'^(.+?) is inactive\.$', r'\1 अब काम पर नहीं है।'),
        # These three all start with a transaction type; see _hi_money.
        (r'^(.+?) of ₹(\S+) added for (.+?)\.$',
         _hi_money('{2} के लिए {0} ₹{1} जोड़ा गया।')),
        (r'^(.+?) (₹\S+) recorded for (.+?)\.$',
         _hi_money('{2} के लिए {0} {1} दर्ज कर लिया गया।')),
        (r'^(.+?) of ₹(\S+) saved for (.+?)\. Payroll updates automatically\.$',
         _hi_money('{2} के लिए {0} ₹{1} सेव हुआ। वेतन अपने-आप बदल जाएगा।')),
        (r'^(.+?) deleted successfully\.$', r'\1 हटा दिया गया।'),
        (r'^(.+?) name is required\.$', r'\1 का नाम ज़रूरी है।'),
        (r'^(.+?) saved successfully\.$', r'\1 सेव हो गया।'),
        # 'state' here is whatever the route chose (enabled, archived,
        # restored...), so this must not insist on a fixed word list.
        (r'^(.+?) (\S+) successfully\.$', r'\1 \2 कर दिया गया।'),
        (r'^(.+?) has been permanently deleted\.$', r'\1 हमेशा के लिए हटा दिया गया।'),
        (r'^(.+?) marked as (.+?) — (.+?)\.$',
         r'\1 पर “\2” लगा दिया गया — \3।'),
        (r'^(.+?) is now (.+?)\.$', r'\1 अब \2 है।'),
        (r'^(.+?) assigned to (.+?)\.$', r'\1 को \2 पर लगा दिया गया।'),
        (r'^(.+?) has no pay rate yet, so payroll will show ₹0 for them '
         r'until one is set\.$',
         r'\1 की मज़दूरी अभी तय नहीं है, इसलिए नियत होने तक वेतन में ₹0 दिखेगा।'),
        (r'^(.+?) now follows the company salary policy\.$',
         r'\1 अब कंपनी के तनख़्वाह नियम पर है।'),
        # Part-settling a month. Three shapes rather than one with a clause
        # plugged in, because a message whose middle can be any of three
        # things has no shape to match on.
        (r'^(.+?): settled in full\.$', r'\1: पूरा चुकता हो गया।'),
        # Loose captures for the amounts: these have to match a real message
        # ("₹10,000 paid") and the placeholder shape the flash test feeds in.
        (r'^(.+?): (.+?) paid, (.+?) still owed\.$',
         r'\1: \2 दिया गया, \3 अभी बाक़ी।'),
        (r'^(.+?): reopened, nothing recorded as paid\.$',
         r'\1: फिर से खोल दिया गया, कुछ भी दिया हुआ दर्ज नहीं।'),
        (r'^That is more than the month is worth \((.+?)\)\. '
         r'Record the extra as an advance instead\.$',
         r'यह महीने की रक़म (\1) से ज़्यादा है। बाक़ी को पेशगी के रूप में दर्ज करें।'),
        # Confirming in person, which is the employer's word and not the
        # worker's — the Hindi keeps that distinction.
        (r'^Marked as handed over to (.+?) in person\.$',
         r'\1 को सामने दिया गया, यह दर्ज हो गया।'),
        (r'^Payments are now counted (.+?)\.$',
         r'भुगतान अब \1 गिना जाएगा।'),
    ],
}

_FLASH_PATTERNS = {
    lang: [(re.compile(p), r) for p, r in entries]
    for lang, entries in _FLASH_PATTERNS_SOURCE.items()
}


_ENGLISH_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November',
                   'December']


def _localise_months(text, lang):
    """Swap English month names inside an already-translated message.

    A message carrying a period ("Payroll for October 2026 ...") keeps the
    month verbatim through the pattern substitution, which would leave one
    English word stranded in a Hindi sentence.
    """
    months = MONTHS.get(lang)
    if not months:
        return text
    for idx, english in enumerate(_ENGLISH_MONTHS):
        if english in text:
            text = text.replace(english, months[idx])
    return text

def translate_flash(text, lang):
    """One flash message, translated on its way to the screen.

    Tries the plain table first, then the shapes that carry a value, then
    the interface table, and otherwise returns the English unchanged — a new
    message added to routes.py shows in English rather than disappearing.

    The interface table is consulted last because a few notices are worded
    exactly like the control that raises them: 'Amount must be greater than
    zero.' is both a message the scanner raises in JavaScript and one the
    endpoint returns in JSON, and one Hindi sentence for it beats two that
    drift apart.
    """
    if not text or lang == DEFAULT_LANGUAGE:
        return text
    text = str(text).strip()
    hit = FLASH_MESSAGES.get(lang, {}).get(text)
    if hit:
        return hit
    for pattern, repl in _FLASH_PATTERNS.get(lang, ()):
        new, count = pattern.subn(repl, text)
        if count:
            return _localise_months(new, lang)
    return TRANSLATIONS.get(lang, {}).get(text, text)


def translate(text, lang):
    """English source string -> the chosen language, or English unchanged."""
    if not text or lang == DEFAULT_LANGUAGE:
        return text
    return TRANSLATIONS.get(lang, {}).get(text, text)


def coverage(lang):
    """How many of the known strings this language actually has.

    Used by the settings screen to be honest about a partial translation
    rather than implying the whole app is translated.
    """
    table = TRANSLATIONS.get(lang)
    if not table:
        return 0, 0
    return len(table), len(TRANSLATIONS.get('hi', {})) or len(table)
