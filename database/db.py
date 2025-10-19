import sqlite3
class User:
    def __init__(self):
        self.conn = sqlite3.connect("Acadex.db")
        self.cur = self.conn.cursor()
        self.cur.execute("PRAGMA foreign_keys = ON;")
        
                
    def create_table(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
            mat_num TEXT PRIMARY KEY UNIQUE NOT NULL,
            name TEXT NOT NULL,
            level INTEGER CHECK(level>=100),
            cgpa REAL NOT NULL,
            password TEXT NOT NULL,
            department TEXT NOT NULL,
            payment_info BOOLEAN DEFAULT "False",
            last_login DATETIME,
            reset_time DATETIME
            )
        """)
        print("Table Created Successfully")
    
    @staticmethod
    def get_key_values(items:dict):
       keys = tuple(keys for keys in items.keys())
       values = tuple(values for values in items.values())    
       pseudo_val = f"{"?,"* len(values)}".rstrip(",")
       place_holder = f"({pseudo_val})" 
       return keys,values,place_holder 
       
    def insert_items(self,table,**items):
       keys,values,place_holder = User.get_key_values(items)
       try:
           self.cur.execute("BEGIN")
           self.cur.execute(f""" 
              INSERT INTO {table} {keys} VALUES {place_holder}
           """, values
           )
           self.conn.commit()
           print("DONE")
       except Exception as e:
           self.conn.rollback()  
           print(e)  
    
    def update_content_by_matnum(self,matnum,table,**content):
        key = list(content.keys())[0]
        value = content[key]
        try:
            self.cur.execute("BEGIN")
            self.cur.execute(f"""
                UPDATE {table} SET {key} = ?
                WHERE mat_num = ?
            """,(value,matnum))
            self.conn.commit()
            print("Updated successfully")
        except Exception as e:
            self.conn.rollback()
            print(e)
            
    
    def get_user(self,table,mat_num):
        self.cur.execute(f"SELECT * FROM {table} WHERE mat_num = ?",(mat_num,))
        values = self.cur.fetchall()
        return values[0]
        
class Courses(User):
    def __init__(self):
         super().__init__()      
    
    def create_table(self):
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS courses(
            course_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num UNIQUE NOT NULL,
            course_code TEXT NOT NULL UNIQUE,
            course_title TEXT UNIQUE NOT NULL,
            grade_unit INTEGER NOT NULL,
            FOREIGN KEY (mat_num) REFERENCES users(mat_num) ON DELETE CASCADE
            )
        """)
       print("Table Created Successfully")   

class Receipts(User):
    def __init__(self):
         super().__init__()      
    
    def create_table(self):
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts(
            receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num UNIQUE NOT NULL,
            level INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            date_added DATETIME NOT NULL,
            FOREIGN KEY (mat_num) REFERENCES users(mat_num) ON DELETE CASCADE
            )
        """)
       print("Table Created Successfully")   

class Results(User):
    def __init__(self):
         super().__init__()      
    
    def create_table(self):
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts(
            result_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num UNIQUE NOT NULL,
            level INTEGER NOT NULL,
            semester TEXT NOT NULL,
            file_path TEXT NOT NULL,
            date_added DATETIME NOT NULL,
            FOREIGN KEY (mat_num) REFERENCES users(mat_num) ON DELETE CASCADE
            )
        """)
       print("Table Created Successfully")   

           
        
if __name__ == "__main__":
    user = User()
    user.create_table()
    user.insert_items("users",mat_num="FUO/23/Csi/22491",name="kudos",level=200,cgpa=3.5,password="22May@2007",department="CSI")       
    user.update_content_by_matnum("FUO/23/Csi/22491","users",payment_info = False)
    print(user.get_user("users","FUO/23/Csi/22491"))
    courses = Courses()
    courses.create_table()
    courses.insert_items("courses",mat_num="FUO/23/Csi/22491",course_code="CSC201",course_title="Programming",grade_unit=2)
    print(courses.get_user("courses","FUO/23/Csi/22491"))

       
             
        