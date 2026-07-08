import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-key-for-dev')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ==========================================
# 📊 データベースモデル設定 (design.md 準拠)
# ==========================================

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True) 
    name = db.Column(db.String(50), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    role = db.Column(db.String(20), default='スタッフ')

class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(50), unique=True, nullable=False)

class Availability(db.Model):
    """勤務希望（スタッフが空いている時間を登録するテーブル）"""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)       
    start_time = db.Column(db.String(10), nullable=False) 
    end_time = db.Column(db.String(10), nullable=False)   

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='未確定')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

# 初期データ作成
def init_master_data():
    db.create_all()
    if not Store.query.first():
        stores = [Store(store_name='渋谷店'), Store(store_name='新宿店'), Store(store_name='池袋店')]
        db.session.add_all(stores)
        db.session.commit()
        
        shibuya = Store.query.filter_by(store_name='渋谷店').first()
        for i in range(1, 21):
            staff = Staff(id=i, name=f"渋谷太郎_{i}", store_id=shibuya.id, role='スタッフ')
            db.session.add(staff)
        db.session.commit()

# ==========================================
# 🛣️ 画面ルート処理
# ==========================================

@app.route('/')
def index():
    if 'staff_id' in session:
        return redirect(url_for('calendar'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        store_name = request.form.get('store_name')
        try:
            staff_id = int(request.form.get('staff_id'))
        except ValueError:
            flash('社員番号は数字で入力してください。', 'danger')
            return redirect(url_for('login'))

        store = Store.query.filter_by(store_name=store_name).first()
        staff = Staff.query.filter_by(id=staff_id, store_id=store.id).first()

        if staff:
            session['staff_id'] = staff.id
            session['staff_name'] = staff.name
            session['store_id'] = store.id
            session['store_name'] = store.store_name
            return redirect(url_for('calendar'))
        else:
            flash('店舗名、または社員番号が正しくありません。', 'danger')
            
    return render_template('login.html', stores=Store.query.all())

# ✨ 🆕 新店舗をデータベースに登録するルート設定
@app.route('/add_store', methods=['POST'])
def add_store():
    new_store_name = request.form.get('new_store_name')
    if new_store_name:
        # すでに同じ名前の店舗がないかチェック
        exists = Store.query.filter_by(store_name=new_store_name).first()
        if not exists:
            new_store = Store(store_name=new_store_name)
            db.session.add(new_store)
            db.session.commit()
            flash(f'店舗「{new_store_name}」を新しく登録しました！', 'success')
        else:
            flash('その店舗名は既に登録されています。', 'warning')
            
    return redirect(url_for('login'))

@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    if 'staff_id' not in session:
        return redirect(url_for('login'))

    staff_id = session['staff_id']
    store_id = session['store_id']

    if request.method == 'POST':
        action_type = request.form.get('action_type') 
        date = request.form.get('date')
        time_range = request.form.get('time_range') 
        start_time, end_time = time_range.split('-')

        # 空き時間の登録
        if action_type == 'register_availability':
            exists = Availability.query.filter_by(staff_id=staff_id, date=date, start_time=start_time, end_time=end_time).first()
            if not exists:
                new_avail = Availability(staff_id=staff_id, date=date, start_time=start_time, end_time=end_time)
                db.session.add(new_avail)
                db.session.commit()
                flash(f'{date} {time_range} を「空き時間」として登録しました！', 'success')
            else:
                flash('その時間帯の空き時間は既に登録されています。', 'warning')

        # シフト希望枠へ入る処理
        elif action_type == 'register_shift':
            existing_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time).all()
            current_staff_ids = [s.staff_id for s in existing_shifts]

            if staff_id in current_staff_ids:
                flash('既にこのシフトに登録されています。', 'warning')
            elif len(current_staff_ids) >= 3:
                flash('【過剰防止】この時間帯は既に3名で確定しているため、追加登録できません。', 'danger')
            else:
                new_shift = Shift(staff_id=staff_id, store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='未確定')
                db.session.add(new_shift)
                db.session.commit()

                # 3人揃ったら自動確定
                updated_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time).all()
                if len(updated_shifts) == 3:
                    for s in updated_shifts:
                        s.status = '確定'
                        db.session.add(Notification(staff_id=s.staff_id, content=f"【シフト確定】{date} {start_time}-{end_time} が確定しました。"))
                    db.session.commit()
                    flash('3名に達したため【シフト確定】しました！', 'success')
                else:
                    flash('シフト希望を登録しました。', 'info')

    all_shifts = Shift.query.filter_by(store_id=store_id).order_by(Shift.date, Shift.start_time).all()
    my_availabilities = Availability.query.filter_by(staff_id=staff_id).order_by(Availability.date).all()
    notif_count = Notification.query.filter_by(staff_id=staff_id).count()

    return render_template('calendar.html', shifts=all_shifts, my_avails=my_availabilities, my_id=staff_id, notif_count=notif_count)

# 【コア機能】欠勤キャンセル ＆ 空いている人限定の通知
@app.route('/cancel/<int:shift_id>')
def cancel(shift_id):
    if 'staff_id' not in session:
        return redirect(url_for('login'))

    target_shift = Shift.query.get(shift_id)
    if target_shift and target_shift.staff_id == session['staff_id']:
        store_id = target_shift.store_id
        date = target_shift.date
        start_time = target_shift.start_time
        end_time = target_shift.end_time

        db.session.delete(target_shift)
        db.session.commit()

        # 残ったメンバーを未確定に戻す
        remaining_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time).all()
        for s in remaining_shifts:
            s.status = '未確定'
        db.session.commit()

        # 人手不足時の【新・通知ロジック】
        if len(remaining_shifts) <= 2:
            already_working_ids = [s.staff_id for s in remaining_shifts]
            
            # 「この日この時間が空いている」と出している人だけをピンポイント抽出
            available_staffs = Availability.query.filter(
                Availability.date == date,
                Availability.start_time == start_time,
                Availability.end_time == end_time,
                Availability.staff_id.not_in(already_working_ids)
            ).all()

            notified_ids = []
            for avail in available_staffs:
                notif = Notification(
                    staff_id=avail.staff_id,
                    content=f"【急募・欠員発生】あなたが空き時間として登録している {date} {start_time}-{end_time} に欠員が出ました。応援に入っていただけませんか？"
                )
                db.session.add(notif)
                notified_ids.append(avail.staff_id)
            
            db.session.commit()

            if notified_ids:
                flash(f'シフトを辞退しました。この時間に【空いているスタッフ（社員番号: {notified_ids}）】限定で応援依頼を送りました。', 'warning')
            else:
                flash('シフトを辞退しました。（現在、この時間帯に空いている登録のあるスタッフはいません）', 'warning')
        else:
            flash('シフトをキャンセルしました。', 'success')

    return redirect(url_for('calendar'))

@app.route('/notifications')
def notifications():
    if 'staff_id' not in session:
        return redirect(url_for('login'))
    my_notifications = Notification.query.filter_by(staff_id=session['staff_id']).order_by(Notification.created_at.desc()).all()
    return render_template('notifications.html', notifications=my_notifications)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        init_master_data()
    app.run(debug=True, port=5000)
