import iris
for q in ["SELECT Name,Type FROM %Dictionary.CompiledProperty WHERE parent='%SYS.Python.SQLResultSet'", "SELECT Name,FormalSpec FROM %Dictionary.CompiledMethod WHERE parent='%SYS.Python.SQLResultSet'"]:
    print(q,list(iris.sql.exec(q)))
