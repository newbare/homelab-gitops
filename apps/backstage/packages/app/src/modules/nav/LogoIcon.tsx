import { makeStyles } from '@material-ui/core';

const useStyles = makeStyles({
  img: {
    height: 40,
    width: 40,
    objectFit: 'contain',
  },
});

export const LogoIcon = () => {
  const classes = useStyles();

  return (
    <img
      className={classes.img}
      src="/logo-resilience-icon.png"
      alt="Resilience Cloud"
    />
  );
};
