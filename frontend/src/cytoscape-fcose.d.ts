// cytoscape-fcose ships without TypeScript types. It is a cytoscape extension registered
// with cytoscape.use(fcose); its layout options are passed as a plain object.
declare module "cytoscape-fcose" {
  const fcose: cytoscape.Ext;
  export default fcose;
}
