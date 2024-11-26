from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import razorpay
from datetime import datetime
import random
from razorpay_config import RAZORPAY_API_KEY, RAZORPAY_API_SECRET
from random import choice

app = Flask(__name__)


# RAZORPAY_API_KEY = "your_razorpay_api_key"
# RAZORPAY_API_SECRET = "your_razorpay_api_secret"

# Secret key
razorpay_client = razorpay.Client(auth=(RAZORPAY_API_KEY, RAZORPAY_API_SECRET))
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost/myadmin'  # MySQL database connection
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    pass_hash = db.Column(db.String(200), nullable=False)  # Store hashed password
    wallet_balance = db.Column(db.Float, nullable=False, default=0)

# GameResult model for generic game results
class GameResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_name = db.Column(db.String(100), default='Dice Roll')
    result = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    user = db.relationship('User', backref='game_results')

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())



with app.app_context():
    db.create_all()

# Routes


@app.route('/send_message', methods=['POST'])
def send_message():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')

    # Validate the input
    if not name or not email or not message:
        return "All fields are required!", 400

    # Save to the database
    try:
        new_message = ContactMessage(name=name, email=email, message=message)
        db.session.add(new_message)
        db.session.commit()
        return redirect(url_for('contact_success'))
    except Exception as e:
        return f"An error occurred: {str(e)}", 500

@app.route('/contact_success')
def contact_success():
    return "Your message has been sent successfully!"

@app.route('/messages')
def view_messages():
    messages = ContactMessage.query.all()
    return {
        "messages": [
            {
                "name": msg.name,
                "email": msg.email,
                "message": msg.message,
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            } for msg in messages
        ]
    }

# Wallet route
@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if request.method == 'POST':
        action = request.form.get('action')
        amount = float(request.form.get('amount', 0))
        if action == 'deposit':
            return redirect(url_for('create_order', amount=amount))
        elif action == 'withdraw' and amount <= user.wallet_balance:
            user.wallet_balance -= amount
            db.session.commit()
            flash('Withdrawal successful!', 'success')
        else:
            flash('Insufficient balance or invalid action!', 'danger')
    return render_template('wallet.html', user=user)

# Create order for Razorpay payment
@app.route('/create_order/<float:amount>', methods=['GET'])
def create_order(amount):
    amount_in_paise = int(amount * 100)  # Convert amount to paise
    order_data = {
        'amount': amount_in_paise,
        'currency': 'INR',
        'payment_capture': '1'
    }
    order = razorpay_client.order.create(data=order_data)
    return render_template('pay.html', order_id=order['id'], amount=amount)

# Payment success route
@app.route('/payment_success', methods=['POST'])
def payment_success():
    payment_id = request.form.get('razorpay_payment_id')
    if not payment_id:
        flash("Payment ID not found!", 'danger')
        return redirect(url_for('wallet'))
    
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    
    user = User.query.get(user_id)
    amount = float(request.form.get('amount', 0))
    user.wallet_balance += amount
    db.session.commit()
    flash("Payment Successful!", 'success')
    return redirect(url_for('wallet'))

# Payment failure route
@app.route('/payment_failed', methods=['POST'])
def payment_failed():
    flash("Payment Failed! Please try again.", 'danger')
    return redirect(url_for('wallet'))

# Account route
@app.route('/account', methods=['GET', 'POST'])
def account():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.name = request.form['name']
        db.session.commit()
        flash('Profile updated successfully.', 'success')
    return render_template('account.html', user=user)

# Promotion route
@app.route('/promo', methods=['GET', 'POST'])
def promotions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        promo_code = request.form['promo_code']
        valid_codes = ["WELCOME100", "WEEKLYCASHBACK", "REFER100"]
        if promo_code in valid_codes:
            flash(f'Promo code "{promo_code}" redeemed successfully!', 'success')
        else:
            flash('Invalid promo code. Please try again.', 'danger')
    return render_template('promo.html')

# Route for displaying game history
@app.route('/game-history')
def game_history():
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Fetch each game type's history from the database
    # color_game_history = ColorGameResult.query.filter_by(user_id=user_id).order_by(ColorGameResult.timestamp.desc()).all()
    odd_even_game_history = OddEvenGameResult.query.filter_by(user_id=user_id).order_by(OddEvenGameResult.timestamp.desc()).all()
    generic_game_history = GameResult.query.filter_by(user_id=user_id).order_by(GameResult.timestamp.desc()).all()

    # Structure data to pass to the template
    all_games_history = {
        # 'color_game': color_game_history,
        'odd_even_game': odd_even_game_history,
        'generic_game': generic_game_history
    }

    # Render the game history template
    return render_template('game_history.html', all_games_history=all_games_history)

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        user = User.query.filter_by(phone=phone).first()
        if user and check_password_hash(user.pass_hash, password):
            session['user_id'] = user.id
            session['name'] = user.name
            return redirect(url_for('account'))
        flash('Invalid login credentials. Please try again.', 'danger')
    return render_template('login.html')

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = request.form['password']
        existing_user = User.query.filter_by(phone=phone).first()
        if existing_user:
            flash('Phone number already registered. Please login.', 'warning')
            return redirect(url_for('login'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(name=name, phone=phone, pass_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully. Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/')
def main():
    return redirect(url_for('home'))

# Privacy, Terms, and About routes
@app.route('/home')
def home():
    return render_template('home.html')
@app.route('/privacy')
def privacy_policy():
    return render_template('privacy.html')


@app.route('/security')
def security():
    return render_template('security.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/color')
def color():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('color.html', User=session)

@app.route('/contact')
def contact_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('contact.html')
    

@app.route('/colorgame')
def colorgame():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('color_game.html', User=session)


@app.route('/dice')
def dice():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('dice.html',User=session)


@app.route('/keno')
def keno():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('keno.html',User=session)


@app.route('/coin')
def coin():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('coin.html',User=session)


@app.route('/oddeven')
def odd_even():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('odd-even.html',User=session)

@app.route('/roll')
def roll():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('roll.html',User=session)


@app.route('/plinko')
def plinko():
    if 'user_id' not in session:
        return render_template(url_for('login'))
    return render_template('plinko.html', User=session)


@app.route('/get_balance', methods=['GET'])
def get_balance():
    user_id = request.args.get('user_id')
    user = User.query.get(user_id)
    if user:
        return jsonify({"balance": user.wallet_balance})
    return jsonify({"error": "User not found"}), 404

@app.route('/update_balance', methods=['POST'])
def update_balance():
    data = request.json
    user_id = data.get("user_id")
    new_balance = data.get("new_balance")

    user = User.query.get(user_id)
    if user:
        user.wallet_balance = new_balance
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "User not found"}), 404



if __name__ == '__main__':
    app.run(debug=True)
