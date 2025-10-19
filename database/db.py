import sqlite3
from typing import Optional
class User:
    def __init__(self):
        self.conn = sqlite3.connect("Acadex.db")
        self.cur = self.conn.cursor()
        self.cur.execute("PRAGMA foreign_keys = ON;")
        
                
    def create_table(self) -> str:
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
            mat_num TEXT UNIQUE NOT NULL,
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
        return "Table Created Successfully"
    
    @staticmethod
    def get_key_values(items:dict,user_id:int = None) -> tuple[tuple,str,tuple]:
       if user_id != None:
            items["user_id"] = user_id
       keys = tuple(keys for keys in items.keys())
       values = tuple(values for values in items.values())    
       pseudo_val = f"{"?,"* len(values)}".rstrip(",") #Generates the amount of placeholders(?) needed
       place_holder = f"({pseudo_val})"
       return keys,values,place_holder 
       
    def insert_items(self,table:str,user_id:int=None,**items) -> str:
       keys,values,place_holder = User.get_key_values(items,user_id)
       try:
           self.cur.execute("BEGIN")
           self.cur.execute(f""" 
              INSERT INTO {table} {keys} VALUES {place_holder}
           """, values
           )
           self.conn.commit()
           return "DONE"
       except Exception as e:
           self.conn.rollback()  
           print(e)  
    
    def update_content_by_matnum(self,matnum:str,table:str,**content) -> str:
        key = list(content.keys())[0]
        value = content[key]
        try:
            self.cur.execute("BEGIN")
            self.cur.execute(f"""
                UPDATE {table} SET {key} = ?
                WHERE mat_num = ?
            """,(value,matnum))
            self.conn.commit()
            return "Updated successfully"
        except Exception as e:
            self.conn.rollback()
            print(e)
            
    def get_user_content(self,table:str,mat_num:str) -> tuple:
        try:
            self.cur.execute(f"SELECT * FROM {table} WHERE mat_num = ?",(mat_num,))
            values = self.cur.fetchall()
            return values[0]
        except IndexError:
            return f"User:{mat_num} not in database"
    
    def delete_table(self,table:str) -> str:
        self.cur.execute("DROP TABLE ?",table)
        return f"{table} dropped"
    
    def delete_user(self,table:str,matnum:str) -> str:
        self.cur.execute(f"SELECT user_id FROM users WHERE mat_num = ?",(matnum,))
        user_id = self.cur.fetchone()[0]
        self.cur.execute(f"DELETE FROM {table} WHERE user_id = ?",(user_id,))
        return f"USER:{matnum} has been removed"
        
class Courses(User):
    def __init__(self):
         super().__init__()      
    
    def create_table(self) -> str:
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS courses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num TEXT UNIQUE NOT NULL,
            user_id INTEGER UNIQUE NOT NULL,
            course_code TEXT NOT NULL UNIQUE,
            course_title TEXT UNIQUE NOT NULL,
            grade_unit INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
       return "Table Created Successfully"  
    
    def insert_items(self,table:str,matnum:str,**items):
        self.cur.execute("SELECT user_id FROM users WHERE mat_num = ?",(matnum,))
        user_id = self.cur.fetchone()[0]
        return super().insert_items(table,user_id,**items)

class Receipts(Courses):
    def __init__(self):
         super().__init__()      
    
    def create_table(self) -> str:
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num TEXT UNIQUE NOT NULL,
            user_id INTEGER UNIQUE NOT NULL,
            level INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            date_added DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
       return "Table Created Successfully"  

class Results(Courses):
    def __init__(self):
         super().__init__()      
    
    def create_table(self) -> str:
       self.cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mat_num TEXT UNIQUE NOT NULL,
            level INTEGER NOT NULL,
            semester TEXT NOT NULL,
            file_path TEXT NOT NULL,
            date_added DATETIME NOT NULL,
            user_id INTEGER UNIQUE NOT NULL, 
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
       return "Table Created Successfully"  

#Factory Method Implementation
def table_factory(table_name:str) -> User|Courses|Results|Receipts:
        try:
            if table_name == "user":
                return User()
            elif table_name == "courses":
                return Courses()
            elif table_name == "results":
                return Results()
            elif table_name == "receipts":
                return Receipts()
            else:
                raise Exception(f"{table_name} is not part of the database")
        except Exception as e:
            print(e)    
        
if __name__ == "__main__":
    user = table_factory("user")
    user.create_table()
    user.insert_items("users",mat_num="FUO/23/Csi/22491",name="kudos",level=200,cgpa=3.5,password="22May@2007",department="CSI")       
    user.update_content_by_matnum("FUO/23/Csi/22491","users",payment_info = False)
    print(user.get_user_content("users",""))
    courses = table_factory("courses")
    courses.create_table()
    courses.insert_items("courses","FUO/23/Csi/22491",course_code="CSC201",course_title="Programming",grade_unit=2)
    print(user.delete_user("users","FUO/23/Csi/22491"))
    print("hey")
    print(courses.get_user_content("courses","FUO/23/Csi/22491"))

       
             
        