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
        # Stored enum values shown with .title() in templates
        'Holiday': 'त्योहार/छुट्टी',
        'Weather': 'मौसम',
        'Emergency': 'आपात',
        'Maintenance': 'मरम्मत',
        'Completed': 'पूरा हुआ',
        'On_hold': 'रुका हुआ',
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
            return new
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
