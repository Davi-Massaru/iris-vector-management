Class VectorAdmin.SeedTask Extends %SYS.Task.Definition
{
Parameter TaskName = "Vector recipe seed";
Property RecipeRevision As %String(MAXLEN = 32);

Method OnTask() As %Status [ Language = python ]
{
    import sys
    sys.path.insert(0, '/usr/irissys/csp/vector-admin')
    from vector_admin.recipes import run_recipe
    run_recipe(self.RecipeRevision)
    return 1
}
}
