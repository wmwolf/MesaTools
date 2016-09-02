import mesatools.database as db

if __name__ == '__main__':
    if not db.have_database():
        db.make_database()
    my_db = db.MesaDatabase()
    interface = db.InlistDbHandler(my_db)
    print(interface.search_doc('use_Ledoux_criterion').name)
