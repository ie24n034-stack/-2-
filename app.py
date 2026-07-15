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
# 📊 データベースモデル設定
# ==========================================

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True) 
    name = db.Column(db.String(50), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    role = db.Column(db.String(20), default='スタッフ')
    staff_number = db.Column(db.Integer, nullable=False)
    shifts = db.relationship('Shift', backref='staff', cascade='all, delete-orphan')

class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(50), unique=True, nullable=False)
    staffs = db.relationship('Staff', backref='store', cascade='all, delete-orphan')
    shifts = db.relationship('Shift', backref='store', cascade='all, delete-orphan')

class Availability(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.String(20), nullable=False)       
    start_time = db.Column(db.String(10), nullable=False) 
    end_time = db.Column(db.String(10), nullable=False)   
    created_at = db.Column(db.DateTime, default=datetime.now)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='CASCADE'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='未確定') # '未確定', '確定', 'リザーブ'

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='CASCADE'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

# 初期データ作成
def init_master_data():
    db.create_all()
    if not Store.query.first():
        shibuya = Store(store_name='渋谷店')
        db.session.add(shibuya)
        db.session.commit()
        
        for i in range(1, 21):
            staff = Staff(id=i, name=f"渋谷太郎_{i}", store_id=shibuya.id, role='スタッフ', staff_number=i)
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
            input_number = int(request.form.get('staff_id'))
        except ValueError:
            flash('社員番号は数字で入力してください。', 'danger')
            return redirect(url_for('login'))

        store = Store.query.filter_by(store_name=store_name).first()
        if not store:
            flash('店舗名が正しくありません。', 'danger')
            return redirect(url_for('login'))

        staff = Staff.query.filter_by(staff_number=input_number, store_id=store.id).first()

        if staff:
            session['staff_id'] = staff.id
            session['staff_name'] = staff.name
            session['store_id'] = store.id
            session['store_name'] = store.store_name
            return redirect(url_for('calendar'))
        else:
            flash(f'「{store_name}」に社員番号 {input_number} は登録されていません。', 'danger')
            
    return render_template('login.html', stores=Store.query.all())

@app.route('/add_staff', methods=['POST'])
def add_staff():
    store_name = request.form.get('store_name')
    staff_name = request.form.get('staff_name')
    
    store = Store.query.filter_by(store_name=store_name).first()
    if not store:
        flash('選択した店舗が見つかりませんでした。', 'danger')
        return redirect(url_for('login'))
        
    if staff_name:
        max_staff_num = db.session.query(db.func.max(Staff.staff_number)).filter(Staff.store_id == store.id).scalar()
        next_staff_number = (max_staff_num or 0) + 1
        
        max_id = db.session.query(db.func.max(Staff.id)).scalar() or 0
        new_id = max_id + 1
        
        new_staff = Staff(
            id=new_id,
            name=staff_name,
            store_id=store.id,
            role='スタッフ',
            staff_number=next_staff_number
        )
        db.session.add(new_staff)
        db.session.commit()
        
        flash(f'🎉「{store_name}」に {staff_name} さんを新しく登録しました！社員番号は 【 {next_staff_number} 】 です。', 'success')
    else:
        flash('名前を入力してください。', 'warning')
        
    return redirect(url_for('login'))

# ✨【新規追加】退職スタッフのデータ一括削除（シフト自動補填連動）
@app.route('/delete_staff', methods=['POST'])
def delete_staff():
    store_name = request.form.get('store_name')
    try:
        staff_number = int(request.form.get('staff_number'))
    except ValueError:
        flash('社員番号は数字で入力してください。', 'danger')
        return redirect(url_for('login'))
        
    store = Store.query.filter_by(store_name=store_name).first()
    if not store:
        flash('店舗が見つかりませんでした。', 'danger')
        return redirect(url_for('login'))
        
    staff = Staff.query.filter_by(staff_number=staff_number, store_id=store.id).first()
    if not staff:
        flash(f'「{store_name}」に社員番号 {staff_number} のスタッフは見つかりませんでした。', 'warning')
        return redirect(url_for('login'))
        
    staff_id = staff.id
    staff_name = staff.name
    
    # 💡 賢い連動：辞める人が入っていたすべてのシフトに対して、穴埋め処理を個別に実行する
    my_shifts = Shift.query.filter_by(staff_id=staff_id).all()
    for ts in my_shifts:
        date = ts.date
        start_time = ts.start_time
        end_time = ts.end_time
        was_confirmed = (ts.status == '確定')
        
        db.session.delete(ts)
        db.session.commit()
        
        if was_confirmed:
            # 先着順でリザーブメンバーを1名繰り上げる
            next_reserve = db.session.query(Shift).\
                join(Availability, Shift.staff_id == Availability.staff_id).\
                filter(
                    Shift.store_id == store.id,
                    Shift.date == date,
                    Shift.start_time == start_time,
                    Shift.end_time == end_time,
                    Shift.status == 'リザーブ',
                    Availability.date == date,
                    Availability.start_time == start_time,
                    Availability.end_time == end_time
                ).\
                order_by(Availability.created_at.asc()).first()

            if next_reserve:
                next_reserve.status = '確定'
                db.session.add(Notification(
                    staff_id=next_reserve.staff_id,
                    content=f"【シフト繰り上げ確定】{date} {start_time}-{end_time} に退職による欠員が出たため、リザーブ枠からあなたのシフトが【確定】に繰り上がりました！"
                ))
                db.session.commit()
                continue # 次のシフト処理へ

        # 繰り上げるリザーブがいない場合、残ったメンバーを未確定に戻し、他スタッフへ急募を送る
        remaining_shifts = Shift.query.filter_by(store_id=store.id, date=date, start_time=start_time, end_time=end_time, status='確定').all()
        for s in remaining_shifts:
            db.session.add(Notification(
                staff_id=s.staff_id,
                content=f"【欠員発生】一緒に参加している {date} {start_time}-{end_time} のシフトに退職による欠員が出ました。"
            ))
            s.status = '未確定'
        db.session.commit()

        if len(remaining_shifts) <= 2:
            already_working_ids = [s.staff_id for s in remaining_shifts]
            exclude_ids = already_working_ids + [staff_id]
            
            available_staffs = Availability.query.filter(
                Availability.date == date,
                Availability.start_time == start_time,
                Availability.end_time == end_time,
                Availability.staff_id.not_in(exclude_ids)
            ).all()

            for avail in available_staffs:
                db.session.add(Notification(
                    staff_id=avail.staff_id,
                    content=f"【急募・欠員発生】あなたが空き時間として登録している {date} {start_time}-{end_time} に退職による欠員が出ました。応援に入っていただけませんか？"
                ))
            db.session.commit()

    # 残りの通知データと空き時間データを一括削除
    Notification.query.filter_by(staff_id=staff_id).delete()
    Availability.query.filter_by(staff_id=staff_id).delete()
    
    # スタッフ本体を削除
    db.session.delete(staff)
    db.session.commit()
    
    # 💡 もし今ログインしている本人の番号を削除した場合は自動ログアウトさせる
    if session.get('staff_id') == staff_id:
        session.clear()
        flash(f'自身のアカウント（{staff_name}さん）を削除したため自動ログアウトしました。', 'info')
    else:
        flash(f'👤 {staff_name} さん（社員番号: {staff_number}）のデータを完全に削除し、関連シフトの調整を行いました。', 'success')
        
    return redirect(url_for('login'))

@app.route('/add_store', methods=['POST'])
def add_store():
    new_store_name = request.form.get('new_store_name')
    if new_store_name:
        exists = Store.query.filter_by(store_name=new_store_name).first()
        if not exists:
            new_store = Store(store_name=new_store_name)
            db.session.add(new_store)
            db.session.commit()
            
            max_staff_id = db.session.query(db.func.max(Staff.id)).scalar() or 0
            start_id = max_staff_id + 1
            
            for i in range(1, 21):
                current_id = start_id + (i - 1)
                new_staff = Staff(
                    id=current_id, 
                    name=f"{new_store_name}スタッフ_{i}", 
                    store_id=new_store.id, 
                    role='スタッフ',
                    staff_number=i
                )
                db.session.add(new_staff)
            db.session.commit()
            
            flash(f'店舗「{new_store_name}」を登録し、社員番号(1〜20)を自動割り当てしました！', 'success')
        else:
            flash('その店舗名は既に登録されています。', 'warning')
            
    return redirect(url_for('login'))

@app.route('/delete_store', methods=['POST'])
def delete_store():
    store_name_to_delete = request.form.get('store_name')
    if store_name_to_delete == '渋谷店':
        flash('「渋谷店」は初期店舗のため削除できません。', 'danger')
        return redirect(url_for('login'))
        
    store = Store.query.filter_by(store_name=store_name_to_delete).first()
    if store:
        staff_ids = [s.id for s in store.staffs]
        Notification.query.filter(Notification.staff_id.in_(staff_ids)).delete(synchronize_session=False)
        Availability.query.filter(Availability.staff_id.in_(staff_ids)).delete(synchronize_session=False)
        
        db.session.delete(store)
        db.session.commit()
        flash(f'店舗「{store_name_to_delete}」と、所属する全データを削除しました。', 'success')
    else:
        flash('削除対象の店舗が見つかりませんでした。', 'warning')
        
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

        if action_type == 'register_availability':
            confirmed_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='確定').all()
            already_in_shift = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time, staff_id=staff_id).first()
            exists_avail = Availability.query.filter_by(staff_id=staff_id, date=date, start_time=start_time, end_time=end_time).first()
            
            if not exists_avail:
                new_avail = Availability(staff_id=staff_id, date=date, start_time=start_time, end_time=end_time)
                db.session.add(new_avail)

                if not already_in_shift:
                    if len(confirmed_shifts) >= 3:
                        new_shift = Shift(staff_id=staff_id, store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='リザーブ')
                        db.session.add(new_shift)
                        db.session.commit()
                        
                        db.session.add(Notification(
                            staff_id=staff_id,
                            content=f"【リザーブ登録】{date} {start_time}-{end_time} はすでに3名で埋まっています。あなたはこのシフトに入れることは確定していませんが、欠員が出たらあなたはこのシフトに入ることになります。"
                        ))
                        db.session.commit()
                        flash(f'{date} {time_range} をリザーブ（補欠）枠として保存しました。', 'info')
                    
                    else:
                        new_shift = Shift(staff_id=staff_id, store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='未確定')
                        db.session.add(new_shift)
                        db.session.commit()

                        unconfirmed_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='未確定').all()
                        if len(unconfirmed_shifts) == 3:
                            for s in unconfirmed_shifts:
                                s.status = '確定'
                                db.session.add(Notification(staff_id=s.staff_id, content=f"【シフト確定】{date} {start_time}-{end_time} が確定しました。"))
                            db.session.commit()
                            flash(f'{date} {time_range} を登録し、3名に達したため【シフト確定】しました！', 'success')
                        else:
                            flash(f'{date} {time_range} を登録し、自動でシフトへ組み込みました。', 'success')
                else:
                    db.session.commit()
                    flash(f'{date} {time_range} の空き時間を登録しました。', 'success')
            else:
                flash('その時間帯の空き時間は既に登録されています。', 'warning')

    all_shifts = Shift.query.filter_by(store_id=store_id).order_by(Shift.date, Shift.start_time).all()
    my_availabilities = Availability.query.filter_by(staff_id=staff_id).order_by(Availability.date).all()
    notif_count = Notification.query.filter_by(staff_id=staff_id).count()

    return render_template('calendar.html', shifts=all_shifts, my_avails=my_availabilities, my_id=staff_id, notif_count=notif_count)

@app.route('/cancel/<int:shift_id>')
def cancel(shift_id):
    if 'staff_id' not in session:
        return redirect(url_for('login'))

    target_shift = Shift.query.get(shift_id)
    leaver_staff_id = session['staff_id']

    if target_shift and target_shift.staff_id == leaver_staff_id:
        store_id = target_shift.store_id
        date = target_shift.date
        start_time = target_shift.start_time
        end_time = target_shift.end_time
        was_confirmed = (target_shift.status == '確定')

        db.session.delete(target_shift)
        db.session.commit()

        if was_confirmed:
            next_reserve = db.session.query(Shift).\
                join(Availability, Shift.staff_id == Availability.staff_id).\
                filter(
                    Shift.store_id == store_id,
                    Shift.date == date,
                    Shift.start_time == start_time,
                    Shift.end_time == end_time,
                    Shift.status == 'リザーブ',
                    Availability.date == date,
                    Availability.start_time == start_time,
                    Availability.end_time == end_time
                ).\
                order_by(Availability.created_at.asc()).first()

            if next_reserve:
                next_reserve.status = '確定'
                db.session.add(Notification(
                    staff_id=next_reserve.staff_id,
                    content=f"【シフト繰り上げ確定】{date} {start_time}-{end_time} に欠員が出たため、リザーブ枠からあなたのシフトが【確定】に繰り上がりました！"
                ))
                db.session.commit()
                flash(f'シフトを辞退しました。リザーブ枠から先着順で次のスタッフが自動繰り上げ確定しました。', 'success')
                return redirect(url_for('calendar'))

        remaining_shifts = Shift.query.filter_by(store_id=store_id, date=date, start_time=start_time, end_time=end_time, status='確定').all()
        
        for s in remaining_shifts:
            db.session.add(Notification(
                staff_id=s.staff_id,
                content=f"【欠員発生】あなたが参加している {date} {start_time}-{end_time} のシフトに欠員が出ました。"
            ))
            s.status = '未確定'
        db.session.commit()

        if len(remaining_shifts) <= 2:
            already_working_ids = [s.staff_id for s in remaining_shifts]
            exclude_ids = already_working_ids + [leaver_staff_id]
            
            available_staffs = Availability.query.filter(
                Availability.date == date,
                Availability.start_time == start_time,
                Availability.end_time == end_time,
                Availability.staff_id.not_in(exclude_ids)
            ).all()

            for avail in available_staffs:
                db.session.add(Notification(
                    staff_id=avail.staff_id,
                    content=f"【急募・欠員発生】あなたが空き時間として登録している {date} {start_time}-{end_time} に欠員が出ました。応援に入っていただけませんか？"
                ))
            db.session.commit()
            flash('シフトを辞退しました。同時間帯のスタッフに欠員通知を送り、他の空いているスタッフへヘルプ通知を送りました。', 'warning')
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
