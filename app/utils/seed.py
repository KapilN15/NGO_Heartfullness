from datetime import date, timedelta
import random
from app.models import User, Member, Category, Session, Attendance, AuditLog
from app import db


def seed_data():
    try:
    
        if User.query.first():
    
            return
    
    except Exception:
    
        return

    users_data = [
        ('sa1', 'passsa1', 'super_admin',      'Super Admin One'),
        ('sa2', 'passsa2', 'super_admin',      'Super Admin Two'),
        ('sa3', 'passsa3', 'super_admin',      'Super Admin Three'),
        ('ad1', 'passad1', 'admin',            'Admin One'),
        ('ad2', 'passad2', 'admin',            'Admin Two'),
        ('co1', 'passco1', 'coordinator',      'Coordinator One'),
        ('co2', 'passco2', 'coordinator',      'Coordinator Two'),
        ('tr1', 'passtr1', 'trainer',          'Trainer One'),
        ('tr2', 'passtr2', 'trainer',          'Trainer Two'),
        ('tr3', 'passtr3', 'trainer',          'Trainer Three'),
    ]

    created_users = []
    for username, password, role, full_name in users_data:
        u = User(username=username, role=role, full_name=full_name, status='active')
        u.set_password(password)
        db.session.add(u)
        created_users.append(u)
    db.session.commit()

    # Super admins are peers with equal standing - demo data ownership is
    # rotated evenly across all three so none of them looks like the
    # "primary" or "founder" account.
    super_admin_ids = [created_users[0].id, created_users[1].id, created_users[2].id]

    # Member Categories
    cat_names = ['Meditation', 'Youth Program', 'Wellness Session', 'Community Service', 'Leadership Training']
    categories = []
    for i, cn in enumerate(cat_names):
        cat = Category(name=cn, description=f'{cn} activities', status='active',
                        created_by=super_admin_ids[i % len(super_admin_ids)])
        db.session.add(cat)
        categories.append(cat)
    db.session.commit()

    # Sessions reuse the same Category records created above (member
    # categories), since Session.category_id now references the
    # categories table directly.
    cat_objects = categories

    # Members
    names = [
        'Arjun Sharma', 'Priya Patel', 'Ravi Kumar', 'Sunita Singh', 'Mohan Das',
        'Kavitha Reddy', 'Suresh Naidu', 'Lakshmi Iyer', 'Rajesh Gupta', 'Anjali Mehta',
        'Vikram Rao', 'Deepa Nair', 'Anil Joshi', 'Pooja Verma', 'Sanjay Tiwari',
        'Meena Pillai', 'Karthik Balaji', 'Radha Krishnan', 'Dinesh Malhotra', 'Usha Pandey',
        'Srinivas Rao', 'Geetha Kumari', 'Mahesh Babu', 'Nandini Rao', 'Venkat Ramaiah',
        'Saranya Devi', 'Subramaniam K', 'Kamala Devi', 'Chandrasekhar N', 'Pavithra S'
    ]
    genders = ['Male', 'Female']
    religions = ['Hindu', 'Muslim', 'Christian', 'Sikh', 'Buddhist']
    areas = ['KARUR', 'TRICHY', 'COIMBATORE', 'MADURAI', 'CHENNAI', 'SALEM', 'ERODE', 'TIRUPUR']

    member_objects = []
    for i, name in enumerate(names):
        m = Member(
            member_id=f'M{(i+1):04d}',
            full_name=name,
            gender=random.choice(genders),
            age=random.randint(18, 65),
            religion=random.choice(religions),
            mobile_number=f'9{random.randint(100000000, 999999999)}',
            area=random.choice(areas),
            join_date=date.today() - timedelta(days=random.randint(0, 365)),
            status='active' if i < 25 else 'inactive',
            created_by=super_admin_ids[i % len(super_admin_ids)]
        )
        assigned_cats = random.sample(categories, random.randint(1, min(3, len(categories))))
        for cat in assigned_cats:
            m.categories.append(cat)
        db.session.add(m)
        member_objects.append(m)
    db.session.commit()

    # Sessions
    session_names = [
        'Morning Meditation', 'Youth Leadership', 'Wellness Workshop', 'Community Outreach',
        'Advanced Meditation', 'Teen Program', 'Health Awareness', 'Volunteer Training',
        'Stress Management', 'Mindfulness Retreat'
    ]
    statuses = ['completed', 'completed', 'completed', 'scheduled', 'scheduled',
                'draft', 'cancelled', 'completed', 'scheduled', 'draft']

    session_objects = []
    for i, (sname, sstatus) in enumerate(zip(session_names, statuses)):
        s = Session(
            session_id=f'S{(i+1):04d}',
            session_name=sname,
            category_id=cat_objects[i % len(cat_objects)].id,
            date=date.today() + timedelta(days=i*3 - 15),
            start_time='09:00',
            end_time='11:00',
            venue=random.choice(['Main Hall', 'Community Center', 'Park', 'School Ground']),
            status=sstatus,
            attendance_locked=(sstatus == 'completed'),
            created_by=super_admin_ids[i % len(super_admin_ids)]
        )
        db.session.add(s)
        session_objects.append(s)
    db.session.commit()

    for s in session_objects:
        if s.status == 'completed':
            session_cat = s.category
            eligible_members = [m for m in member_objects if session_cat in m.categories and m.status == 'active'][:20]
            for j, m in enumerate(eligible_members):
                att = Attendance(
                    session_id=s.id,
                    member_id=m.id,
                    status=random.choice(['present', 'present', 'present', 'absent']),
                    marked_by=super_admin_ids[j % len(super_admin_ids)]
                )
                db.session.add(att)
    db.session.commit()

    log = AuditLog(user_id=None, username='system', role='system',
                   action='System Initialized', description='Database seeded with initial data.')
    db.session.add(log)
    db.session.commit()
