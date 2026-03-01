from flask import Flask, render_template, request, redirect, session
import mysql.connector
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "secret123"

# ── Database connection ──
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Alkakiit194@",
    database="hotel_db"
)

# ── ALWAYS use this function to get a fresh cursor ──
def get_cursor():
    global db
    if not db.is_connected():
        db.reconnect()
    return db.cursor(dictionary=True)


# ════════════════════════════════════════
#  PUBLIC HOME PAGE
# ════════════════════════════════════════
@app.route('/')
def home():
    if 'admin' in session:
        return redirect('/dashboard')
    return render_template('login.html')


@app.route('/rooms')
def rooms():
    cursor = get_cursor()
    cursor.execute("SELECT * FROM rooms WHERE status='Available'")
    rooms = cursor.fetchall()
    cursor.close()
    return render_template('home.html', rooms=rooms)


# ════════════════════════════════════════
#  LOGIN
# ════════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = get_cursor()
        cursor.execute(
            "SELECT * FROM admin WHERE username=%s AND password=%s",
            (username, password)
        )
        user = cursor.fetchone()
        cursor.close()

        if user:
            session['admin'] = username
            return redirect('/dashboard')
        else:
            return "Invalid Credentials"

    return render_template('login.html')


# ════════════════════════════════════════
#  LOGOUT
# ════════════════════════════════════════
@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect('/')


# ════════════════════════════════════════
#  DASHBOARD
@app.route('/dashboard')
def dashboard():
    if 'admin' not in session:
        return redirect('/')

    tab = request.args.get('tab', 'home')
    cursor = get_cursor()

    # =============================
    # NEW BOOKING TAB
    # =============================
    if tab == 'new-booking':
        cursor.execute("SELECT * FROM customers")
        customers = cursor.fetchall()

        cursor.execute("SELECT * FROM rooms WHERE status='Available'")
        rooms = cursor.fetchall()

        cursor.close()

        return render_template(
            'dashboard.html',
            tab='new-booking',
            customers=customers,
            rooms=rooms
        )

    # =============================
    # ROOMS TAB
    # =============================
    if tab == 'rooms':
        cursor.execute("SELECT * FROM rooms")
        rooms = cursor.fetchall()
        cursor.close()
        return render_template(
            'dashboard.html',
            tab='rooms',
            rooms=rooms
        )

    # =============================
    # DASHBOARD OVERVIEW (Default)
    # =============================

    # Total Revenue
    cursor.execute("""
        SELECT SUM(total_amount) AS revenue
        FROM bookings
        WHERE booking_status = 'Confirmed'
    """)
    revenue = cursor.fetchone()
    total_revenue = revenue['revenue'] if revenue['revenue'] else 0

    # Revenue grouped by room
    cursor.execute("""
        SELECT rooms.room_number, SUM(bookings.total_amount) AS total
        FROM bookings
        JOIN rooms ON bookings.room_id = rooms.room_id
        WHERE bookings.booking_status = 'Confirmed'
        GROUP BY rooms.room_number
    """)
    revenue_data = cursor.fetchall()
    room_labels    = [str(row['room_number']) for row in revenue_data]
    revenue_values = [float(row['total']) for row in revenue_data]

    # Room counts
    cursor.execute("SELECT COUNT(*) AS total FROM rooms")
    total_rooms = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM rooms WHERE status='Available'")
    available_rooms = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM rooms WHERE status='Booked'")
    booked_rooms = cursor.fetchone()['total']

    # Total customers
    cursor.execute("SELECT COUNT(*) AS total FROM customers")
    total_customers = cursor.fetchone()['total']

    # Occupancy by room type
    cursor.execute("SELECT room_type, COUNT(*) AS total FROM rooms GROUP BY room_type")
    room_totals = cursor.fetchall()

    cursor.execute("""
        SELECT room_type, COUNT(*) AS booked
        FROM rooms WHERE status = 'Booked'
        GROUP BY room_type
    """)
    room_booked = cursor.fetchall()

    cursor.close()

    total_dict  = {row['room_type']: row['total']  for row in room_totals}
    booked_dict = {row['room_type']: row['booked'] for row in room_booked}

    deluxe_total    = total_dict.get('Deluxe', 0)
    suite_total     = total_dict.get('Suite', 0)
    standard_total  = total_dict.get('Standard', 0)
    deluxe_booked   = booked_dict.get('Deluxe', 0)
    suite_booked    = booked_dict.get('Suite', 0)
    standard_booked = booked_dict.get('Standard', 0)

    deluxe_pct   = int((deluxe_booked   / deluxe_total)   * 100) if deluxe_total   else 0
    suite_pct    = int((suite_booked    / suite_total)    * 100) if suite_total    else 0
    standard_pct = int((standard_booked / standard_total) * 100) if standard_total else 0

    total_all   = deluxe_total + suite_total + standard_total
    booked_all  = deluxe_booked + suite_booked + standard_booked
    overall_pct = int((booked_all / total_all) * 100) if total_all else 0

    return render_template(
        'dashboard.html',
        tab='home',
        revenue=total_revenue,
        room_labels=room_labels,
        revenue_values=revenue_values,
        total_rooms=total_rooms,
        available_rooms=available_rooms,
        booked_rooms=booked_rooms,
        total_customers=total_customers,
        deluxe_pct=deluxe_pct,
        suite_pct=suite_pct,
        standard_pct=standard_pct,
        overall_pct=overall_pct
    )

# ════════════════════════════════════════
#  ADD ROOM
# ════════════════════════════════════════
@app.route('/add-room', methods=['GET', 'POST'])
def add_room():
    if request.method == 'POST':
        room_number = request.form.get('room_number')
        room_type   = request.form.get('room_type')
        price       = request.form.get('price')
        status      = request.form.get('status', 'Available')

        image    = request.files.get('image')
        filename = None
        if image and image.filename != '':
            filename      = secure_filename(image.filename)
            upload_folder = os.path.join(app.root_path, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            image.save(os.path.join(upload_folder, filename))

        cursor = get_cursor()
        cursor.execute("""
            INSERT INTO rooms (room_number, room_type, price, status, image)
            VALUES (%s, %s, %s, %s, %s)
        """, (room_number, room_type, price, status, filename))
        db.commit()
        cursor.close()

        return redirect('/view-rooms')

    return render_template('add rooms.html')


# ════════════════════════════════════════
#  VIEW ROOMS
# ════════════════════════════════════════
@app.route('/view-rooms')
def view_rooms():
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("SELECT * FROM rooms")
    rooms = cursor.fetchall()
    cursor.close()

    return render_template('view rooms.html', rooms=rooms)


# ════════════════════════════════════════
#  DELETE ROOM
# ════════════════════════════════════════
@app.route('/delete-room/<int:room_id>')
def delete_room(room_id):
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("DELETE FROM rooms WHERE room_id = %s", (room_id,))
    db.commit()
    cursor.close()

    return redirect('/view-rooms')


# ════════════════════════════════════════
#  EDIT ROOM
# ════════════════════════════════════════
@app.route('/edit-room/<int:room_id>', methods=['GET', 'POST'])
def edit_room(room_id):
    if 'admin' not in session:
        return redirect('/')

    if request.method == 'POST':
        room_type = request.form['room_type']
        price     = request.form['price']
        status    = request.form['status']

        cursor = get_cursor()
        cursor.execute("""
            UPDATE rooms
            SET room_type=%s, price=%s, status=%s
            WHERE room_id=%s
        """, (room_type, price, status, room_id))
        db.commit()
        cursor.close()

        return redirect('/view-rooms')

    cursor = get_cursor()
    cursor.execute("SELECT * FROM rooms WHERE room_id=%s", (room_id,))
    room = cursor.fetchone()
    cursor.close()

    return render_template('edit rooms.html', room=room)


# ════════════════════════════════════════
#  BOOK ROOM (Admin)
# ════════════════════════════════════════
@app.route('/book-room/<int:room_id>', methods=['GET', 'POST'])
def book_room(room_id):
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("SELECT * FROM rooms WHERE room_id=%s", (room_id,))
    room = cursor.fetchone()

    cursor.execute("SELECT * FROM customers")
    customers = cursor.fetchall()
    cursor.close()

    if request.method == 'POST':
        customer_id = request.form['customer_id']
        check_in    = request.form['check_in']
        check_out   = request.form['check_out']

        date1 = datetime.strptime(check_in,  "%Y-%m-%d")
        date2 = datetime.strptime(check_out, "%Y-%m-%d")
        days  = (date2 - date1).days
        total_amount = days * float(room['price'])

        cursor = get_cursor()
        cursor.execute("""
            INSERT INTO bookings (customer_id, room_id, check_in, check_out, total_amount)
            VALUES (%s, %s, %s, %s, %s)
        """, (customer_id, room_id, check_in, check_out, total_amount))
        db.commit()

        cursor.execute(
            "UPDATE rooms SET status='Booked' WHERE room_id=%s", (room_id,)
        )
        db.commit()
        cursor.close()

        return redirect('/view-rooms')

    return render_template('book rooms.html', room=room, customers=customers)


# ════════════════════════════════════════
#  VIEW BOOKINGS
# ════════════════════════════════════════
@app.route('/view-bookings')
def view_bookings():
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("""
        SELECT bookings.booking_id,
               customers.name,
               rooms.room_number,
               bookings.check_in,
               bookings.check_out,
               bookings.total_amount,
               bookings.booking_status
        FROM bookings
        JOIN customers ON bookings.customer_id = customers.customer_id
        JOIN rooms     ON bookings.room_id     = rooms.room_id
    """)
    bookings = cursor.fetchall()
    cursor.close()

    return render_template('view bookings.html', bookings=bookings)


# ════════════════════════════════════════
#  INVOICE
# ════════════════════════════════════════
@app.route('/invoice/<int:booking_id>')
def invoice(booking_id):
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("""
        SELECT bookings.*, customers.name, customers.phone,
               rooms.room_number, rooms.room_type
        FROM bookings
        JOIN customers ON bookings.customer_id = customers.customer_id
        JOIN rooms     ON bookings.room_id     = rooms.room_id
        WHERE bookings.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()
    cursor.close()

    return render_template('invoice.html', booking=booking)


# ════════════════════════════════════════
#  PUBLIC BOOKING
# ════════════════════════════════════════
@app.route('/public-book/<int:room_id>', methods=['GET', 'POST'])
def public_book(room_id):
    cursor = get_cursor()
    cursor.execute("SELECT * FROM rooms WHERE room_id=%s", (room_id,))
    room = cursor.fetchone()
    cursor.close()

    if request.method == 'POST':
        name      = request.form['name']
        phone     = request.form['phone']
        email     = request.form['email']
        check_in  = request.form['check_in']
        check_out = request.form['check_out']

        date1 = datetime.strptime(check_in,  "%Y-%m-%d")
        date2 = datetime.strptime(check_out, "%Y-%m-%d")
        days  = (date2 - date1).days
        total_amount = days * float(room['price'])

        cursor = get_cursor()

        # Insert customer
        cursor.execute("""
            INSERT INTO customers (name, phone, email)
            VALUES (%s, %s, %s)
        """, (name, phone, email))
        customer_id = cursor.lastrowid

        # Check overlapping booking
        cursor.execute("""
            SELECT * FROM bookings
            WHERE room_id = %s
            AND booking_status = 'Confirmed'
            AND (check_in < %s AND check_out > %s)
        """, (room_id, check_out, check_in))
        existing_booking = cursor.fetchone()

        if existing_booking:
            cursor.close()
            return "Room not available for selected dates!"

        # Insert booking
        cursor.execute("""
            INSERT INTO bookings
            (customer_id, room_id, check_in, check_out, total_amount, booking_status)
            VALUES (%s, %s, %s, %s, %s, 'Confirmed')
        """, (customer_id, room_id, check_in, check_out, total_amount))
        booking_id = cursor.lastrowid

        # Update room status
        cursor.execute(
            "UPDATE rooms SET status='Booked' WHERE room_id=%s", (room_id,)
        )
        db.commit()
        cursor.close()

        return redirect(f'/booking-success/{booking_id}')

    return render_template('public.html', room=room)


# ════════════════════════════════════════
#  BOOKING SUCCESS
# ════════════════════════════════════════
@app.route('/booking-success/<int:booking_id>')
def booking_success(booking_id):
    cursor = get_cursor()
    cursor.execute("""
        SELECT bookings.*, customers.name, rooms.room_number
        FROM bookings
        JOIN customers ON bookings.customer_id = customers.customer_id
        JOIN rooms     ON bookings.room_id     = rooms.room_id
        WHERE bookings.booking_id = %s
    """, (booking_id,))
    booking = cursor.fetchone()
    cursor.close()

    return render_template('booking success.html', booking=booking)


# ════════════════════════════════════════
#  CUSTOMERS
# ════════════════════════════════════════
@app.route('/customers')
def customers():
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("""
        SELECT c.*, COUNT(b.booking_id) AS total_bookings
        FROM customers c
        LEFT JOIN bookings b ON c.customer_id = b.customer_id
        GROUP BY c.customer_id
        ORDER BY c.created_at DESC
    """)
    customer_list = cursor.fetchall()
    cursor.close()

    return render_template('customers.html', customers=customer_list)


# ════════════════════════════════════════
#  DELETE CUSTOMER
# ════════════════════════════════════════
@app.route('/delete-customer/<int:id>')
def delete_customer(id):
    if 'admin' not in session:
        return redirect('/')

    cursor = get_cursor()
    cursor.execute("DELETE FROM customers WHERE customer_id = %s", (id,))
    db.commit()
    cursor.close()

    return redirect('/customers')
   
  

# =============================
# BOOKING TAB
# =============================
@app.route('/admin-booking', methods=['POST'])
def admin_booking():
    if 'admin' not in session:
        return redirect('/')

    name = request.form['name']
    phone = request.form['phone']
    email = request.form['email']

    room_id = request.form['room_id']
    check_in = request.form['check_in']
    check_out = request.form['check_out']

    cursor = get_cursor()

    # INSERT NEW CUSTOMER
    cursor.execute("""
        INSERT INTO customers (name, phone, email)
        VALUES (%s, %s, %s)
    """, (name, phone, email))

    customer_id = cursor.lastrowid

    # GET ROOM PRICE
    cursor.execute("SELECT price FROM rooms WHERE room_id=%s", (room_id,))
    room = cursor.fetchone()

    from datetime import datetime
    date1 = datetime.strptime(check_in, "%Y-%m-%d")
    date2 = datetime.strptime(check_out, "%Y-%m-%d")
    days = (date2 - date1).days

    total_amount = days * float(room['price'])

    # INSERT BOOKING
    cursor.execute("""
        INSERT INTO bookings
        (customer_id, room_id, check_in, check_out, total_amount, booking_status)
        VALUES (%s, %s, %s, %s, %s, 'Confirmed')
    """, (customer_id, room_id, check_in, check_out, total_amount))

    cursor.execute("UPDATE rooms SET status='Booked' WHERE room_id=%s", (room_id,))
    db.commit()
    cursor.close()

    return redirect('/dashboard')


# ════════════════════════════════════════
#  RUN
# ════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True)
