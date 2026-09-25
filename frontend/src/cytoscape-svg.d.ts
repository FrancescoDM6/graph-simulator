// cytoscape-svg ships without TypeScript types. Registered with cytoscape.use(); adds cy.svg().
declare module "cytoscape-svg" {
  const cytoscapeSvg: cytoscape.Ext;
  export default cytoscapeSvg;
}
