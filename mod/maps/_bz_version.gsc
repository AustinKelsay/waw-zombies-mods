// The build stamps the commit in the staged copy of this module.
bz_get_build_version()
{
	return "0.5.0";
}

bz_get_build_commit()
{
	return "dev";
}

bz_get_build_id()
{
	return bz_get_build_version() + "-" + bz_get_build_commit();
}
