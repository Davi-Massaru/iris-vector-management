Class VectorFixture.Mapped Extends %Persistent
{
Property Embedding As %Vector(DATATYPE = "DOUBLE", LEN = 3);

Storage Default
{
<DataLocation>^VectorFixtureMappedD</DataLocation>
<IdLocation>^VectorFixtureMappedD</IdLocation>
<IndexLocation>^VectorFixtureMappedI</IndexLocation>
<StreamLocation>^VectorFixtureMappedS</StreamLocation>
<Type>%Storage.Persistent</Type>
}
}
