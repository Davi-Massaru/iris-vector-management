/// Acceptance fixture only: at most 50 ms of sleep per invocation, no expensive work.
Class VectorFixture.TestDelay Extends %RegisteredObject
{
ClassMethod Wait(id As %Integer) As %Integer [ SqlProc ]
{
    hang .05
    quit id
}
}
