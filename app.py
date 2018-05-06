from flask import Flask, make_response, render_template, flash, redirect, url_for, session, request, logging
from data import Stocks
from flask_mysqldb import MySQL
from wtforms import Form, DateField, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
import datetime

# BEGIN EXPERIMENTAL SECTION **************************
import matplotlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt, mpld3
import pandas_datareader
import pandas_datareader.data as web
from io import BytesIO
import random

import seaborn as sns
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
# END EXPERIMENTAL SECTION******************************
app = Flask(__name__)

# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'stockwave'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
# init MySQL
mysql = MySQL(app)

@app.route('/')
def index():
    return render_template('home.html')

# @app.route('/about')
# def about():
#     return render_template('about.html')

@app.route('/stocks')
def stocks():
    cur = mysql.connection.cursor()
    result = cur.execute("SELECT * FROM stocks")
    stocks = cur.fetchall()
    cur.close()

    if result > 0:
        return render_template('stocks.html', stocks=stocks)
    else:
        msg = 'No Stocks Found'
        return render_template('stocks.html', msg=msg)

@app.route('/stock/<string:id>/')
def stock(id):
    cur = mysql.connection.cursor()
    result = cur.execute("SELECT * FROM stocks WHERE id = %s", [id])
    stock = cur.fetchone()
    cur.close()

    return render_template('stock.html', data=stock)

class RegisterForm(Form):
    name = StringField('Name', [validators.length(min=1, max=50)])
    username = StringField('Username', [validators.length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')

# need to fix bug to disallow users to register multiple times
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        cur = mysql.connection.cursor()

        result = cur.execute("SELECT * FROM users WHERE email = %s", [email])
        if result == 0:
            cur.execute("INSERT INTO users(name, email, username, password) VALUES(%s, %s, %s, %s)", (name, email, username, password))
            mysql.connection.commit()
            cur.close()
            flash('You are now registered and can log in', 'success')
            session['logged_in'] = True
            session['username'] = username
        else:
            flash('This e-mail has already been registered', 'danger')

        return redirect(url_for('dashboard'))
    return render_template('register.html', form=form)

# user login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']

        cur = mysql.connection.cursor()
        result = cur.execute("SELECT * FROM users WHERE username = %s", [username])

        if result > 0:
            # get stored hash
            data = cur.fetchone()
            password = data['password']
            cur.close()

            # compare Passwords
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = username

                flash("You are now logged in", "success")
                return redirect(url_for('dashboard'))
            else:
                error = "Invalid Login"
                return render_template('login.html', error=error)
        else:
            error = "Username not found"
            return render_template('login.html', error=error)

    return render_template('login.html')

# check if user is logged in // creates a wrap passing in function as 'f'
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap

@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@is_logged_in
def dashboard():
    cur = mysql.connection.cursor()
    result = cur.execute("SELECT * FROM stocks")
    stocks = cur.fetchall()
    cur.close()

    stocks = list(filter(lambda stocks: stocks['username'] == session['username'], stocks))

    if result > 0:
        return render_template('dashboard.html', stocks=stocks)
    else:
        msg = 'No stocks found'
        return render_template('dashboard.html', msg=msg)

class StockForm(Form):
    ticker = StringField('Stock Symbol', [validators.length(min=1, max=5)])
    start_date = DateField('Start Date', [validators.required()])
    end_date = DateField('End Date', [validators.required()])

@app.route('/add_stock', methods=['GET', 'POST'])
@is_logged_in
def add_stock():
    form = StockForm(request.form)
    if request.method == 'POST' and form.validate():
        ticker = form.ticker.data
        start_date = form.start_date.data
        end_date = form.end_date.data

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO stocks(ticker, start_date, end_date, username, create_date) VALUES(%s, %s, %s, %s, %s)", (ticker, start_date, end_date, session['username'], datetime.date.today()))
        mysql.connection.commit()
        cur.close()

        data = web.DataReader(ticker, 'morningstar', start_date, end_date)

        df = data.reset_index()
        fig = Figure()
        axis = fig.add_subplot(1, 1, 1)
        # x_attribute = df.index.names[1]
        x_attribute = 'Date'
        y_attribute = 'High'
        sns.stripplot(data=df, x=x_attribute, y=y_attribute, ax=axis, jitter=True)
        axis.set_xlabel(x_attribute)
        axis.set_ylabel(y_attribute)
        canvas = FigureCanvas(fig)
        output = BytesIO()
        canvas.print_png(output)
        response = make_response(output.getvalue())
        response.mimetype = 'image/png'
        return response

        return render_template('stock.html', data = data)

    return render_template('add_stock.html', form=form)

@app.route('/edit_stock/<string:id>', methods=['GET', 'POST'])
@is_logged_in
def edit_stock(id):
    cur = mysql.connection.cursor()
    result = cur.execute("SELECT * FROM stocks WHERE id = %s", [id])
    stock = cur.fetchone()
    cur.close()

    form = StockForm(request.form)
    form.ticker.data = stock['ticker']
    form.start_date.data = stock['start_date']
    form.end_date.data = stock['end_date']

    if request.method == 'POST' and form.validate():
        ticker = request.form['ticker']
        start_date = request.form['start_date']

        cur = mysql.connection.cursor()
        cur.execute("UPDATE stocks SET ticker=%s, start_date=%s, end_date=%s WHERE id = %s", (ticker, start_date, end_date, id))
        mysql.connection.commit()
        cur.close()

        flash('Stocks Updated', 'success')

        return redirect(url_for('dashboard'))

    return render_template('edit_stock.html', form=form)

@app.route('/delete_stock/<string:id>', methods=['POST'])
@is_logged_in
def delete_stock(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM stocks WHERE id = %s", [id])
    mysql.connection.commit()
    cur.close()

    flash('stock Deleted', 'success')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.secret_key='secret123'
    app.run(debug=True)
