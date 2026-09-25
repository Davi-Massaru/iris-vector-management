Class VectorFixture.StringIds Extends %Persistent
{
Property Code As %String;
Property Embedding As %Vector(DATATYPE = "DOUBLE", LEN = 3);
Index CodeKey On Code [ IdKey ];
}
