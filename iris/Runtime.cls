Class VectorAdmin.Runtime Extends %RegisteredObject
{
ClassMethod BeginBudget(seconds As %Integer) As %String
{
    if $get(^||VectorAdminBudget)'="" quit ""
    set token="VAdmin"_$job_"x"_$increment(^||VectorAdminSequence)
    lock +^VectorAdminBudget($job,token):1
    if '$test throw ##class(%Exception.General).%New("Budget lock unavailable")
    set ^||VectorAdminBudget=token
    do ##class(%SYSTEM.Event).Create(token)
    job ..WatchBudget($job,token,seconds)
    quit token
}

ClassMethod EndBudget(token As %String)
{
    quit:token=""
    lock +^VectorAdminCancel($job):2
    if '$test throw ##class(%Exception.General).%New("Cancellation still pending")
    lock -^VectorAdminBudget($job,token)
    set ^||VectorAdminBudget=""
    if ##class(%SYSTEM.Event).Defined(token) { do ##class(%SYSTEM.Event).Signal(token,"") }
    lock -^VectorAdminCancel($job)
}

ClassMethod WatchBudget(pid As %Integer, token As %String, seconds As %Integer)
{
    set result=##class(%SYSTEM.Event).Wait(token,seconds)
    if result=0 {
        lock +^VectorAdminCancel(pid):2
        if $test {
            lock +^VectorAdminBudget(pid,token):0
            if $test { lock -^VectorAdminBudget(pid,token) }
            else { do $system.SQL.CancelQuery(pid,"",1) }
            lock -^VectorAdminCancel(pid)
        }
    }
    do ##class(%SYSTEM.Event).Delete(token)
}

ClassMethod StartOperation(id As %String) As %Integer
{
    job ..RunOperation(id)
    quit $zchild
}

ClassMethod SearchSlot() As %Integer
{
    for slot=0:1:1 {
        lock +^VectorAdminSearch(slot):0
        if $test quit
    }
    quit $select($test:slot,1:-1)
}

ClassMethod ReleaseSearch(slot As %Integer)
{
    lock -^VectorAdminSearch(slot)
}

ClassMethod MaintenanceLock(acquire As %Boolean) As %Boolean
{
    if acquire { lock +^VectorAdminMaintenance:0 quit $test }
    lock -^VectorAdminMaintenance
    quit 1
}

ClassMethod SeedLock(target As %String, acquire As %Boolean) As %Boolean
{
    if acquire { lock +^VectorAdminSeedLock(target):0 quit $test }
    lock -^VectorAdminSeedLock(target)
    quit 1
}

ClassMethod SeedBegin()
{
    tstart
}

ClassMethod SeedCommit()
{
    tcommit
}

ClassMethod SeedRollback()
{
    if $tlevel { trollback 1 }
}

ClassMethod RunOperation(id As %String) [ Language = python ]
{
    import sys
    sys.path.insert(0, '/usr/irissys/csp/vector-admin')
    from vector_admin.indexes import run_operation
    run_operation(id)
}
}
